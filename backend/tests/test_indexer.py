import io
import os
import sqlite3

import numpy as np
import pytest
from PIL import Image

import embedding
import indexer
import storage
from tests.helpers import BLUE, RED, solid_image_bytes


@pytest.fixture(autouse=True)
def clean_indexer_state():
    indexer.reset_state()
    yield
    indexer.reset_state()


@pytest.fixture()
def log_id(client):
    cid = client.post("/api/categories", json={"name": "手套"}).json()["id"]
    return client.post("/api/logs", data={"category_id": cid}).json()["id"]


def upload(client, log_id, *files):
    resp = client.post(f"/api/logs/{log_id}/images", files=[("files", f) for f in files])
    assert resp.status_code == 201, resp.text
    return resp.json()


def png(name, color):
    return (name, solid_image_bytes(color), "image/png")


def embedding_rows(db_conn):
    return db_conn.execute("SELECT image_id, model, vector FROM image_embeddings ORDER BY image_id").fetchall()


def test_process_pending_writes_vectors_for_uploaded_images(client, fake_embedder, log_id, db_conn):
    images = upload(client, log_id, png("a.png", RED), png("b.png", BLUE))
    assert indexer.process_pending() == 2

    rows = embedding_rows(db_conn)
    assert sorted(r["image_id"] for r in rows) == sorted(i["id"] for i in images)
    for r in rows:
        assert r["model"] == embedding.MODEL_ID
        vec = embedding.from_blob(r["vector"])
        assert vec.shape == (embedding.DIM,)
        assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-5


def test_process_pending_is_idempotent(client, fake_embedder, log_id):
    upload(client, log_id, png("a.png", RED))
    assert indexer.process_pending() == 1
    assert indexer.process_pending() == 0


def test_images_created_with_log_are_indexed(client, fake_embedder):
    cid = client.post("/api/categories", json={"name": "手套"}).json()["id"]
    resp = client.post("/api/logs", data={"category_id": cid}, files=[("files", png("a.png", RED))])
    assert resp.status_code == 201
    assert indexer.process_pending() == 1


def test_deleting_image_cascades_to_embedding(client, fake_embedder, log_id, db_conn):
    [image] = upload(client, log_id, png("a.png", RED))
    indexer.process_pending()
    assert client.delete(f"/api/images/{image['id']}").status_code == 204
    assert embedding_rows(db_conn) == []


def test_vectors_from_another_model_count_as_pending(client, fake_embedder, log_id, db_conn):
    upload(client, log_id, png("a.png", RED))
    indexer.process_pending()
    db_conn.execute("UPDATE image_embeddings SET model = 'old-model'")
    db_conn.commit()

    assert indexer.count_pending(db_conn, 1) == 1
    assert indexer.process_pending() == 1
    assert [r["model"] for r in embedding_rows(db_conn)] == [embedding.MODEL_ID]
    assert indexer.count_pending(db_conn, 1) == 0


def test_soft_deleted_logs_are_not_indexed(client, fake_embedder, log_id, db_conn):
    upload(client, log_id, png("a.png", RED))
    assert client.delete(f"/api/logs/{log_id}").status_code == 204
    assert indexer.count_pending(db_conn, 1) == 0
    assert indexer.process_pending() == 0


def test_non_image_file_is_skipped_and_not_counted_as_pending(client, fake_embedder, log_id, db_conn):
    upload(client, log_id, ("notes.txt", b"just some text", "text/plain"))
    assert indexer.count_pending(db_conn, 1) == 1  # 还没试过
    assert indexer.process_pending() == 0
    assert indexer.count_pending(db_conn, 1) == 0  # 试过、解码失败，不再算待处理
    assert embedding_rows(db_conn) == []


def test_image_deleted_during_inference_is_not_written(client, log_id, db_conn):
    [image] = upload(client, log_id, png("a.png", RED))

    def embed_then_delete(img):
        # 模拟推理的几秒钟里，用户在别的请求里删掉了这张图
        other = sqlite3.connect(storage.user_db_path(1))
        other.execute("PRAGMA foreign_keys=ON")
        other.execute("DELETE FROM images WHERE id = ?", (image["id"],))
        other.commit()
        other.close()
        return np.ones(embedding.DIM, dtype=np.float32)

    embedding.set_embedder(embed_then_delete)
    try:
        assert indexer.process_pending() == 0  # 不抛异常
    finally:
        embedding.set_embedder(None)
    assert embedding_rows(db_conn) == []


def test_process_pending_without_model_does_nothing(client, log_id, db_conn):
    upload(client, log_id, png("a.png", RED))
    assert indexer.process_pending() == 0
    assert indexer.count_pending(db_conn, 1) == 1


def test_upload_still_works_without_model(client, log_id):
    [image] = upload(client, log_id, png("a.png", RED))
    assert image["log_id"] == log_id


def test_uploads_wake_the_indexer(client, log_id, monkeypatch):
    calls = []
    monkeypatch.setattr(indexer, "notify", lambda: calls.append(1))
    upload(client, log_id, png("a.png", RED))
    cid = client.post("/api/categories", json={"name": "衣服"}).json()["id"]
    client.post("/api/logs", data={"category_id": cid}, files=[("files", png("b.png", BLUE))])
    assert len(calls) == 2


def _sideways_phone_jpeg_bytes():
    exif = Image.Exif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    Image.new("RGB", (1600, 1200), RED).save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


@pytest.mark.parametrize("remove_thumb", [False, True])
def test_indexed_images_are_rotated_upright(client, log_id, remove_thumb):
    """查询照片会按 EXIF 摆正，库里的图也必须摆正，否则同一张照片自己都搜不到自己。"""
    import thumbnail

    [image] = upload(client, log_id, ("p.jpg", _sideways_phone_jpeg_bytes(), "image/jpeg"))
    if remove_thumb:  # 缩略图不存在时回退到原图，也要摆正
        os.remove(os.path.join(thumbnail.thumb_dir(storage.user_upload_dir(1)), image["filename"]))

    sizes = []

    def recording(img):
        sizes.append(img.size)
        return np.ones(embedding.DIM, dtype=np.float32)

    embedding.set_embedder(recording)
    try:
        assert indexer.process_pending() == 1
    finally:
        embedding.set_embedder(None)
    width, height = sizes[0]
    assert height > width


def _second_user(username="second"):
    import accounts
    conn = accounts.connect()
    uid = accounts.create_user(conn, username, "password-2")
    conn.close()
    storage.provision_user(uid)
    return uid


def _insert_image_for(uid, color):
    """绕过 HTTP 直接给某个账号放一张图（此时还没有第二个会话可用）。"""
    import uuid
    name = f"{uuid.uuid4().hex}.png"
    up = storage.user_upload_dir(uid)
    with open(os.path.join(up, name), "wb") as f:
        f.write(solid_image_bytes(color))
    conn = sqlite3.connect(storage.user_db_path(uid))
    cid = conn.execute("INSERT INTO categories (name) VALUES ('c')").lastrowid
    lid = conn.execute("INSERT INTO logs (category_id) VALUES (?)", (cid,)).lastrowid
    iid = conn.execute(
        "INSERT INTO images (log_id, filename, original_name) VALUES (?, ?, 'x.png')", (lid, name)
    ).lastrowid
    conn.commit()
    conn.close()
    return iid


def _vectors(uid):
    conn = sqlite3.connect(storage.user_db_path(uid))
    rows = conn.execute("SELECT image_id FROM image_embeddings ORDER BY image_id").fetchall()
    conn.close()
    return [r[0] for r in rows]


def test_each_user_gets_own_index(client, fake_embedder, log_id):
    [mine] = upload(client, log_id, png("a.png", RED))
    other = _second_user()
    theirs = _insert_image_for(other, BLUE)

    assert indexer.process_pending() == 2
    assert _vectors(1) == [mine["id"]]
    assert _vectors(other) == [theirs]


def test_inactive_user_is_skipped_until_reactivated(client, fake_embedder):
    import accounts
    other = _second_user()
    _insert_image_for(other, BLUE)
    conn = accounts.connect()
    accounts.set_active(conn, other, False)
    assert indexer.process_pending() == 0
    accounts.set_active(conn, other, True)
    conn.close()
    assert indexer.process_pending() == 1


def test_failed_image_ids_are_tracked_per_user(client, fake_embedder, log_id):
    """两个账号都有 id=1 的图：一个解码失败，不能连累另一个。"""
    upload(client, log_id, ("notes.txt", b"not an image", "text/plain"))
    other = _second_user()
    _insert_image_for(other, BLUE)
    assert indexer.process_pending() == 1
    assert _vectors(other) == [1]


def test_broken_user_db_does_not_stop_others(client, fake_embedder, log_id):
    upload(client, log_id, png("a.png", RED))
    other = _second_user()
    with open(storage.user_db_path(other), "wb") as f:
        f.write(b"this is not sqlite")
    assert indexer.process_pending() == 1
