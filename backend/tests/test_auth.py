from datetime import timedelta

import pytest

import accounts
import ratelimit
from tests.conftest import TEST_PASSWORD


def login(c, username="babelingz", password=TEST_PASSWORD):
    return c.post("/api/auth/login", json={"username": username, "password": password})


def test_health_needs_no_login(anon_client):
    assert anon_client.get("/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/api/categories", "/api/logs", "/api/auth/me"])
def test_business_api_requires_login(anon_client, path):
    assert anon_client.get(path).status_code == 401


def test_login_sets_httponly_cookie(anon_client):
    resp = login(anon_client)
    assert resp.status_code == 200
    assert resp.json() == {"username": "babelingz"}
    cookie = resp.headers["set-cookie"]
    assert "piclog_session=" in cookie
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()
    assert "Max-Age=2592000" in cookie
    assert anon_client.get("/api/auth/me").json() == {"username": "babelingz"}
    assert anon_client.get("/api/categories").status_code == 200


@pytest.mark.parametrize("username,password", [
    ("babelingz", "wrong-password"),
    ("nobody", TEST_PASSWORD),
])
def test_bad_credentials_give_same_message(anon_client, username, password):
    resp = login(anon_client, username, password)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "账号或密码错误"


def test_logout(client):
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_logout_without_session_is_fine(anon_client):
    assert anon_client.post("/api/auth/logout").status_code == 204


def test_deactivated_user_session_is_rejected(client):
    conn = accounts.connect()
    accounts.set_active(conn, 1, False)
    conn.close()
    assert client.get("/api/categories").status_code == 401
    assert login(client).status_code == 401


def test_password_reset_revokes_sessions(client):
    conn = accounts.connect()
    accounts.set_password(conn, 1, "new-password-1")
    conn.close()
    assert client.get("/api/categories").status_code == 401
    assert login(client, password="new-password-1").status_code == 200


def test_session_is_renewed_with_new_cookie(client, monkeypatch):
    later = accounts._now() + timedelta(days=2)
    monkeypatch.setattr(accounts, "_now", lambda: later)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert "piclog_session=" in resp.headers.get("set-cookie", "")


def test_no_cookie_rewrite_when_fresh(client):
    assert "set-cookie" not in client.get("/api/auth/me").headers


def test_lockout_after_five_failures(anon_client):
    for _ in range(ratelimit.MAX_FAILURES):
        assert login(anon_client, password="wrong-password").status_code == 401
    resp = login(anon_client)  # 正确密码也不行
    assert resp.status_code == 429


def test_lockout_expires(anon_client, monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(ratelimit, "_clock", lambda: t[0])
    for _ in range(ratelimit.MAX_FAILURES):
        login(anon_client, password="wrong-password")
    assert login(anon_client).status_code == 429
    t[0] += ratelimit.LOCK_SECONDS + 1
    assert login(anon_client).status_code == 200


def test_success_resets_failure_count(anon_client):
    for _ in range(ratelimit.MAX_FAILURES - 1):
        login(anon_client, password="wrong-password")
    assert login(anon_client).status_code == 200
    for _ in range(ratelimit.MAX_FAILURES - 1):
        login(anon_client, password="wrong-password")
    assert login(anon_client).status_code == 200


def test_lockout_is_per_username(anon_client, make_user):
    """所有人可能同一个出口 IP：一个用户名被锁，不能连累别人。"""
    make_user("second")
    for _ in range(ratelimit.MAX_FAILURES):
        login(anon_client, password="wrong-password")
    assert login(anon_client).status_code == 429
    assert login(anon_client, "second", "password-2").status_code == 200


def test_new_user_can_log_in_and_use_app(make_user):
    c = make_user("second")
    assert c.get("/api/auth/me").json() == {"username": "second"}
    assert c.post("/api/categories", json={"name": "x"}).status_code == 201


def test_files_require_login(client):
    from fastapi.testclient import TestClient
    from main import app
    cid = client.post("/api/categories", json={"name": "c"}).json()["id"]
    log = client.post(
        "/api/logs", data={"category_id": cid},
        files=[("files", ("a.png", b"x", "image/png"))],
    ).json()
    name = log["images"][0]["filename"]
    assert TestClient(app).get(f"/api/files/{name}").status_code == 401


def test_request_from_tab_of_another_account_is_rejected(client):
    """旧标签页还以为自己是别的账号：它发来的写请求不能落到当前账号的库里。"""
    resp = client.post(
        "/api/categories", json={"name": "x"}, headers={"X-PicLog-User": "someone_else"}
    )
    assert resp.status_code == 401
    assert client.get("/api/categories").json() == []


def test_matching_user_header_is_accepted(client):
    resp = client.post(
        "/api/categories", json={"name": "x"}, headers={"X-PicLog-User": "babelingz"}
    )
    assert resp.status_code == 201


def test_chinese_username_login_and_header(anon_client, make_user):
    from urllib.parse import quote
    c = make_user("张三")
    assert c.get("/api/auth/me").json() == {"username": "张三"}
    # 前端把用户名 URL 编码后放进请求头（请求头只能是 ASCII）
    ok = c.post("/api/categories", json={"name": "x"}, headers={"X-PicLog-User": quote("张三")})
    assert ok.status_code == 201
    bad = c.post("/api/categories", json={"name": "y"}, headers={"X-PicLog-User": quote("李四")})
    assert bad.status_code == 401
