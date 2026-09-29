import os
import sqlite3

import pytest

import accounts
import bootstrap
import database
import storage
import thumbnail


@pytest.fixture()
def layout(tmp_path, monkeypatch):
    """一套独立的 data/ 与 uploads/，不碰 conftest 的全局目录。"""
    data = tmp_path / "data"
    uploads = tmp_path / "uploads"
    data.mkdir()
    uploads.mkdir()
    monkeypatch.setattr(storage, "DATA_DIR", str(data))
    monkeypatch.setattr(storage, "UPLOAD_ROOT", str(uploads))
    monkeypatch.setenv("INITIAL_USER_PASSWORD", "initial-pass-1")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    return data, uploads


def _make_legacy(data, uploads):
    """造一个单用户时代的部署：旧库里有一条日志一张图，上传目录有原图、缩略图和标记文件。"""
    db = str(data / "piclog.db")
    database.init_db(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO categories (id, name) VALUES (7, '手套')")
    conn.execute("INSERT INTO logs (id, category_id, description) VALUES (42, 7, '旧日志')")
    conn.execute("INSERT INTO images (id, log_id, filename, original_name) VALUES (9, 42, 'abc.jpg', 'a.jpg')")
    conn.commit()
    conn.close()
    (uploads / "abc.jpg").write_bytes(b"original")
    (uploads / "thumbs").mkdir()
    (uploads / "thumbs" / "abc.jpg").write_bytes(b"thumb")
    (uploads / "thumbs" / thumbnail.ORIENTED_MARKER).write_bytes(b"")


def _user1_rows():
    conn = sqlite3.connect(storage.user_db_path(1))
    rows = conn.execute(
        "SELECT l.id, l.description, i.id, i.filename FROM logs l JOIN images i ON i.log_id = l.id"
    ).fetchall()
    conn.close()
    return rows


def test_legacy_data_moves_to_first_user(layout):
    data, uploads = layout
    _make_legacy(data, uploads)

    assert bootstrap.run() == [1]

    assert not (data / "piclog.db").exists()
    assert _user1_rows() == [(42, "旧日志", 9, "abc.jpg")]  # ID 与文件名不变
    up1 = storage.user_upload_dir(1)
    assert open(os.path.join(up1, "abc.jpg"), "rb").read() == b"original"
    assert open(os.path.join(up1, "thumbs", "abc.jpg"), "rb").read() == b"thumb"
    # 标记文件跟着搬走：不会因为「没有标记」再把所有缩略图重建一遍
    assert os.path.exists(os.path.join(up1, "thumbs", thumbnail.ORIENTED_MARKER))
    assert not (uploads / "abc.jpg").exists()
    assert not (uploads / "thumbs").exists()

    conn = accounts.connect()
    user = accounts.authenticate(conn, "babelingz", "initial-pass-1")
    assert user["id"] == 1
    assert accounts.get_meta(conn, bootstrap.LEGACY_FLAG) == "1"
    conn.close()


def test_second_run_changes_nothing(layout):
    data, uploads = layout
    _make_legacy(data, uploads)
    bootstrap.run()
    # 迁移完成后，有人在旧位置又放了个库：不能再被搬
    database.init_db(str(data / "piclog.db"))
    assert bootstrap.run() == [1]
    assert (data / "piclog.db").exists()
    assert _user1_rows() == [(42, "旧日志", 9, "abc.jpg")]


def test_resume_after_partial_move(layout):
    """模拟上次在移动途中断电：库已经移走、原图还在旧位置、账号还没建。"""
    data, uploads = layout
    _make_legacy(data, uploads)
    os.makedirs(storage.user_dir(1))
    os.replace(data / "piclog.db", storage.user_db_path(1))

    assert bootstrap.run() == [1]
    assert _user1_rows() == [(42, "旧日志", 9, "abc.jpg")]
    assert os.path.exists(os.path.join(storage.user_upload_dir(1), "abc.jpg"))


def test_conflict_refuses_to_overwrite(layout):
    data, uploads = layout
    _make_legacy(data, uploads)
    os.makedirs(storage.user_upload_dir(1))
    with open(os.path.join(storage.user_upload_dir(1), "abc.jpg"), "wb") as f:
        f.write(b"someone copied this by hand")

    with pytest.raises(storage.MigrationConflict, match="abc.jpg"):
        bootstrap.run()
    assert (uploads / "abc.jpg").read_bytes() == b"original"


def test_fresh_deploy_creates_empty_first_user(layout):
    assert bootstrap.run() == [1]
    conn = sqlite3.connect(storage.user_db_path(1))
    assert conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0] == 0
    conn.close()
    assert os.path.isdir(os.path.join(storage.user_upload_dir(1), "thumbs"))


def test_missing_initial_password_fails_before_moving_anything(layout, monkeypatch):
    data, uploads = layout
    _make_legacy(data, uploads)
    monkeypatch.delenv("INITIAL_USER_PASSWORD")
    with pytest.raises(bootstrap.BootstrapError, match="INITIAL_USER_PASSWORD"):
        bootstrap.run()
    assert (data / "piclog.db").exists()
    assert (uploads / "abc.jpg").exists()


def test_initial_password_not_needed_once_users_exist(layout, monkeypatch):
    bootstrap.run()
    monkeypatch.delenv("INITIAL_USER_PASSWORD")
    assert bootstrap.run() == [1]


def test_admin_password_written_once_from_env(layout, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    bootstrap.run()
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-2")
    bootstrap.run()
    conn = accounts.connect()
    assert accounts.verify_admin(conn, "admin-pass-1")
    assert not accounts.verify_admin(conn, "admin-pass-2")
    conn.close()


def test_every_user_db_is_initialised_on_startup(layout):
    """账号行已存在但库文件缺失（例如开户时中断）：下次启动会补上。"""
    bootstrap.run()
    conn = accounts.connect()
    uid = accounts.create_user(conn, "second", "password-2")
    conn.close()
    assert bootstrap.run() == [1, uid]
    assert os.path.isfile(storage.user_db_path(uid))


def test_provision_user_is_idempotent(layout):
    storage.provision_user(5)
    conn = sqlite3.connect(storage.user_db_path(5))
    conn.execute("INSERT INTO categories (name) VALUES ('x')")
    conn.commit()
    conn.close()
    storage.provision_user(5)
    conn = sqlite3.connect(storage.user_db_path(5))
    assert conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 1
    conn.close()


def test_invalid_initial_password_fails_before_moving_anything(layout, monkeypatch):
    data, uploads = layout
    _make_legacy(data, uploads)
    monkeypatch.setenv("INITIAL_USER_PASSWORD", "short")
    with pytest.raises(bootstrap.BootstrapError, match="INITIAL_USER_PASSWORD"):
        bootstrap.run()
    assert (data / "piclog.db").exists()
    assert (uploads / "abc.jpg").exists()


def test_warns_when_legacy_db_reappears_after_migration(layout, caplog):
    """迁移后旧位置又出现库：多半是回滚到了旧版本并写入了数据，必须大声提示。"""
    data, uploads = layout
    _make_legacy(data, uploads)
    bootstrap.run()
    database.init_db(str(data / "piclog.db"))
    with caplog.at_level("WARNING", logger="piclog.bootstrap"):
        bootstrap.run()
    assert any("piclog.db" in r.getMessage() for r in caplog.records if r.levelname == "WARNING")
