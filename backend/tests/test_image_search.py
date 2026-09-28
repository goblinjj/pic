import io
import sqlite3

import pytest
from PIL import Image

import embedding
import indexer
from tests.helpers import BLUE, GREEN, PURPLE, RED, mean_color_vector, solid_image_bytes


@pytest.fixture(autouse=True)
def clean_indexer_state():
    indexer.reset_state()
    yield
    indexer.reset_state()


def png(name, color, size=(32, 32)):
    return (name, solid_image_bytes(color, size), "image/png")


def make_log(client, cid, description, *files):
    resp = client.post(
        "/api/logs",
        data={"category_id": cid, "description": description},
        files=[("files", f) for f in files],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def gallery(client, fake_embedder):
    """红日志（红图 + 蓝图）、紫日志、蓝日志、绿日志；全部建好索引。"""
    cid = client.post("/api/categories", json={"name": "手套"}).json()["id"]
    logs = {
        "red": make_log(client, cid, "红手套", png("r.png", RED), png("rb.png", BLUE)),
        "purple": make_log(client, cid, "紫手套", png("p.png", PURPLE)),
        "blue": make_log(client, cid, "蓝手套", png("b.png", BLUE)),
        "green": make_log(client, cid, "绿手套", png("g.png", GREEN)),
    }
    assert indexer.process_pending() == 5
    logs["cid"] = cid
    return logs


def search(client, content, **params):
    return client.post(
        "/api/search/image", params=params, files={"file": ("q.jpg", content, "image/jpeg")}
    )


def test_returns_matching_logs_sorted_and_drops_low_scores(client, gallery):
    resp = search(client, solid_image_bytes(RED))
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    # 红 ≈ 1、紫 ≈ 0.707；蓝、绿 ≈ 0 低于 MIN_SCORE 被丢弃
    assert [it["log"]["id"] for it in items] == [gallery["red"]["id"], gallery["purple"]["id"]]
    assert items[0]["score"] > 0.99
    assert 0.6 < items[1]["score"] < 0.8


def test_each_log_appears_once_with_its_best_image(client, gallery):
    items = search(client, solid_image_bytes(BLUE)).json()["items"]
    ids = [it["log"]["id"] for it in items]
    assert sorted(ids) == sorted({gallery["red"]["id"], gallery["blue"]["id"], gallery["purple"]["id"]})
    red_hit = next(it for it in items if it["log"]["id"] == gallery["red"]["id"])
    blue_image = gallery["red"]["images"][1]  # 红日志里的那张蓝图
    assert red_hit["matched_image"]["id"] == blue_image["id"]
    assert red_hit["score"] > 0.99


def test_hit_carries_full_log_payload(client, gallery):
    hit = search(client, solid_image_bytes(RED)).json()["items"][0]
    assert hit["log"]["description"] == "红手套"
    assert hit["log"]["category_name"] == "手套"
    assert len(hit["log"]["images"]) == 2
    assert "field_values" in hit["log"]


def test_limit(client, gallery):
    items = search(client, solid_image_bytes(RED), limit=1).json()["items"]
    assert len(items) == 1


@pytest.mark.parametrize("limit", [0, 51])
def test_limit_out_of_range_is_rejected(client, gallery, limit):
    assert search(client, solid_image_bytes(RED), limit=limit).status_code == 422


def test_min_score_minus_one_returns_everything(client, gallery):
    items = search(client, solid_image_bytes(RED), min_score=-1).json()["items"]
    assert len(items) == 4


def test_soft_deleted_logs_are_excluded(client, gallery):
    client.delete(f"/api/logs/{gallery['red']['id']}")
    ids = [it["log"]["id"] for it in search(client, solid_image_bytes(RED)).json()["items"]]
    assert gallery["red"]["id"] not in ids


def test_indexed_and_pending_counts(client, gallery):
    body = search(client, solid_image_bytes(RED)).json()
    assert body["indexed"] == 5
    assert body["pending"] == 0

    make_log(client, gallery["cid"], "新的", png("n.png", RED))
    body = search(client, solid_image_bytes(RED)).json()
    assert body["indexed"] == 5
    assert body["pending"] == 1


def test_empty_index_returns_pending_count(client, fake_embedder):
    cid = client.post("/api/categories", json={"name": "手套"}).json()["id"]
    make_log(client, cid, "a", png("a.png", RED))
    make_log(client, cid, "b", png("b.png", BLUE))
    resp = search(client, solid_image_bytes(RED))
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "indexed": 0, "pending": 2}


def test_returns_503_without_model(client):
    resp = search(client, solid_image_bytes(RED))
    assert resp.status_code == 503
    assert resp.json()["detail"] == "以图搜图未启用"


def test_returns_503_when_model_file_is_corrupt(client, monkeypatch, tmp_path):
    bad = tmp_path / "bad.onnx"
    bad.write_bytes(b"not a model")
    monkeypatch.setenv("MODEL_PATH", str(bad))
    embedding._session = None
    resp = search(client, solid_image_bytes(RED))
    assert resp.status_code == 503
    assert resp.json()["detail"] == "以图搜图未启用"


def test_non_image_returns_400(client, fake_embedder):
    resp = search(client, b"definitely not an image")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "无法识别的图片"


def test_truncated_jpeg_returns_400(client, fake_embedder):
    full = solid_image_bytes(RED, size=(200, 200), fmt="JPEG")
    resp = search(client, full[: len(full) // 2])
    assert resp.status_code == 400
    assert resp.json()["detail"] == "无法识别的图片"


def test_oversized_image_returns_400(client, fake_embedder, monkeypatch):
    # 超过 2 倍 MAX_IMAGE_PIXELS 时 Pillow 抛 DecompressionBombError
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    resp = search(client, solid_image_bytes(RED, size=(100, 100)))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "图片尺寸过大"


@pytest.fixture()
def seen_sizes():
    sizes = []

    def recording(img):
        sizes.append(img.size)
        return mean_color_vector(img)

    embedding.set_embedder(recording)
    yield sizes
    embedding.set_embedder(None)


def test_exif_orientation_is_applied(client, seen_sizes):
    # 40×20 的横图，EXIF 标记「顺时针转 90°」：摆正后应是 20×40 的竖图
    exif = Image.Exif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), RED).save(buf, "JPEG", exif=exif.tobytes())
    assert search(client, buf.getvalue()).status_code == 200
    assert seen_sizes == [(20, 40)]


def test_query_image_is_downscaled_to_800(client, seen_sizes):
    assert search(client, solid_image_bytes(RED, size=(2000, 1000))).status_code == 200
    assert seen_sizes == [(800, 400)]


def test_rgba_query_image_is_accepted(client, seen_sizes):
    buf = io.BytesIO()
    Image.new("RGBA", (20, 20), (255, 0, 0, 128)).save(buf, "PNG")
    assert search(client, buf.getvalue()).status_code == 200


def test_constant_number_of_queries(client, gallery):
    """回归护栏：SQL 语句数不随命中条数增长（同 test_log_filter_sort 的做法）。"""
    import database
    from main import app

    statements = []

    def tracing_db():
        conn = sqlite3.connect(database.DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.set_trace_callback(statements.append)
        try:
            yield conn
        finally:
            conn.close()

    def run(min_score):
        statements.clear()
        app.dependency_overrides[database.get_db] = tracing_db
        try:
            resp = search(client, solid_image_bytes(RED), min_score=min_score)
        finally:
            app.dependency_overrides.pop(database.get_db, None)
        return len(resp.json()["items"]), len(statements)

    few_hits, few_statements = run(0.9)    # 只命中红日志
    many_hits, many_statements = run(-1)   # 命中全部 4 条
    assert few_hits == 1 and many_hits == 4
    assert few_statements == many_statements


def test_large_jpeg_query_is_not_decoded_at_full_resolution(client, seen_sizes, monkeypatch):
    """大图直接全尺寸解码会吃掉上百 MB 内存；JPEG 应在解码阶段就缩小。"""
    from PIL import JpegImagePlugin

    loaded = []
    original_load = JpegImagePlugin.JpegImageFile.load

    def spying_load(self):
        loaded.append(self.size)
        return original_load(self)

    monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "load", spying_load)
    resp = search(client, solid_image_bytes(RED, size=(4000, 3000), fmt="JPEG"))
    assert resp.status_code == 200
    assert loaded and max(loaded[0]) < 4000
    assert seen_sizes == [(800, 600)]


def test_oversized_upload_returns_413(client, fake_embedder):
    from routers import search as search_router

    resp = search(client, b"\xff" * (search_router.MAX_QUERY_BYTES + 1))
    assert resp.status_code == 413
    assert resp.json()["detail"] == "图片文件过大"
