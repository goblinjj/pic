import os

import storage
from tests.helpers import RED, solid_image_bytes


def _log_with_image(client):
    cid = client.post("/api/categories", json={"name": "手套"}).json()["id"]
    resp = client.post(
        "/api/logs",
        data={"category_id": cid},
        files=[("files", ("a.png", solid_image_bytes(RED), "image/png"))],
    )
    assert resp.status_code == 201
    return resp.json()["images"][0]["filename"]


def test_original_and_thumbnail_are_served(client):
    name = _log_with_image(client)
    resp = client.get(f"/api/files/{name}")
    assert resp.status_code == 200
    assert resp.content == solid_image_bytes(RED)
    assert "private" in resp.headers["cache-control"]
    thumb = client.get(f"/api/files/thumbs/{name}")
    assert thumb.status_code == 200
    assert thumb.content[:2] == b"\xff\xd8"  # 缩略图统一存成 JPEG


def test_file_on_disk_but_not_in_db_is_404(client):
    _log_with_image(client)
    up = storage.user_upload_dir(1)
    with open(os.path.join(up, "stray.png"), "wb") as f:
        f.write(b"x")
    assert client.get("/api/files/stray.png").status_code == 404


def test_path_traversal_is_404(client):
    _log_with_image(client)
    for path in (
        "/api/files/..%2F..%2F..%2Fdata%2Faccounts.db",
        "/api/files/%2E%2E",
        "/api/files/thumbs/..%2Fabc",
    ):
        assert client.get(path).status_code == 404, path


def test_old_static_uploads_route_is_gone(client):
    name = _log_with_image(client)
    assert client.get(f"/uploads/{name}").status_code == 404
    assert client.get(f"/uploads/thumbs/{name}").status_code == 404


def test_files_with_unusual_legacy_extension_are_served(client, db_conn):
    """旧数据的扩展名来自用户原始文件名，不一定规整。"""
    name = "0123456789abcdef0123456789abcdef.jpg(1)"
    up = storage.user_upload_dir(1)
    with open(os.path.join(up, name), "wb") as f:
        f.write(b"legacy")
    cid = db_conn.execute("INSERT INTO categories (name) VALUES ('c')").lastrowid
    lid = db_conn.execute("INSERT INTO logs (category_id) VALUES (?)", (cid,)).lastrowid
    db_conn.execute(
        "INSERT INTO images (log_id, filename, original_name) VALUES (?, ?, 'x')", (lid, name)
    )
    db_conn.commit()
    assert client.get(f"/api/files/{name}").content == b"legacy"
