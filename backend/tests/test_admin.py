import pytest
from fastapi.testclient import TestClient

import accounts
import ratelimit
import storage
from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_PATH, TEST_PASSWORD

P = f"/{TEST_ADMIN_PATH}"


# 管理员登录成功返回 204（无 body）
def admin_login(c, password=TEST_ADMIN_PASSWORD, username="admin"):
    return c.post(f"{P}/api/login", json={"username": username, "password": password})


@pytest.fixture()
def admin(anon_client):
    assert admin_login(anon_client).status_code == 204
    return anon_client


def test_page_is_served(anon_client):
    resp = anon_client.get(f"{P}/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "no-store" in resp.headers["cache-control"]


def test_path_without_slash_redirects(anon_client):
    resp = anon_client.get(P, follow_redirects=False)
    assert resp.status_code in (307, 308)
    assert resp.headers["location"].endswith(f"{P}/")


def test_admin_routes_hidden_from_openapi(anon_client):
    assert TEST_ADMIN_PATH not in anon_client.get("/openapi.json").text


def test_api_requires_admin_login(anon_client):
    assert anon_client.get(f"{P}/api/users").status_code == 401
    assert anon_client.post(
        f"{P}/api/users", json={"username": "x_user", "password": "password-1"}
    ).status_code == 401


def test_user_session_is_not_admin(client):
    assert client.get(f"{P}/api/users").status_code == 401


@pytest.mark.parametrize("username,password", [
    ("admin", "wrong-password"),
    ("root", TEST_ADMIN_PASSWORD),
])
def test_bad_admin_login(anon_client, username, password):
    resp = admin_login(anon_client, password, username)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "账号或密码错误"


def test_admin_cookie_is_scoped_to_admin_path(anon_client):
    cookie = admin_login(anon_client).headers["set-cookie"]
    assert "piclog_admin=" in cookie
    assert f"Path={P}" in cookie
    assert "HttpOnly" in cookie
    assert "samesite=strict" in cookie.lower()
    assert "Max-Age=43200" in cookie


def test_admin_lockout(anon_client):
    for _ in range(ratelimit.MAX_FAILURES):
        admin_login(anon_client, "wrong-password")
    assert admin_login(anon_client).status_code == 429


def test_admin_logout(admin):
    assert admin.post(f"{P}/api/logout").status_code == 204
    assert admin.get(f"{P}/api/users").status_code == 401


def test_list_users_with_counts(admin, client):
    # client 与 admin 是同一个 TestClient：它同时带着用户 Cookie 和管理员 Cookie
    cid = client.post("/api/categories", json={"name": "c"}).json()["id"]
    client.post("/api/logs", data={"category_id": cid},
                files=[("files", ("a.png", b"not-really-png", "image/png"))])
    lid = client.post("/api/logs", data={"category_id": cid}).json()["id"]
    client.delete(f"/api/logs/{lid}")  # 软删除的不计

    [row] = admin.get(f"{P}/api/users").json()
    assert row["id"] == 1 and row["username"] == "babelingz" and row["is_active"] is True
    assert row["log_count"] == 1 and row["image_count"] == 1
    assert "created_at" in row


def test_create_user_then_login(admin):
    resp = admin.post(f"{P}/api/users", json={"username": "carol", "password": "carol-pass-1"})
    assert resp.status_code == 201
    uid = resp.json()["id"]
    c = TestClient(admin.app)
    assert c.post("/api/auth/login", json={"username": "carol", "password": "carol-pass-1"}).status_code == 200
    assert c.get("/api/categories").json() == []
    assert storage.user_db_path(uid).endswith(f"users/{uid}/piclog.db")


def test_create_duplicate_is_409(admin):
    resp = admin.post(f"{P}/api/users", json={"username": "babelingz", "password": "password-9"})
    assert resp.status_code == 409


@pytest.mark.parametrize("body", [
    {"username": "No", "password": "password-1"},
    {"username": "valid_name", "password": "short"},
])
def test_create_invalid_is_400(admin, body):
    assert admin.post(f"{P}/api/users", json=body).status_code == 400


def test_reset_password(admin):
    user_client = TestClient(admin.app)
    user_client.post("/api/auth/login", json={"username": "babelingz", "password": TEST_PASSWORD})
    assert admin.put(f"{P}/api/users/1/password", json={"password": "brand-new-1"}).status_code == 204
    assert user_client.get("/api/categories").status_code == 401
    assert user_client.post(
        "/api/auth/login", json={"username": "babelingz", "password": "brand-new-1"}
    ).status_code == 200


def test_reset_password_too_short_is_400(admin):
    assert admin.put(f"{P}/api/users/1/password", json={"password": "short"}).status_code == 400


def test_deactivate_and_reactivate(admin):
    user_client = TestClient(admin.app)
    user_client.post("/api/auth/login", json={"username": "babelingz", "password": TEST_PASSWORD})
    assert admin.put(f"{P}/api/users/1/active", json={"is_active": False}).status_code == 204
    assert user_client.get("/api/categories").status_code == 401
    assert admin.get(f"{P}/api/users").json()[0]["is_active"] is False
    assert admin.put(f"{P}/api/users/1/active", json={"is_active": True}).status_code == 204
    assert user_client.post(
        "/api/auth/login", json={"username": "babelingz", "password": TEST_PASSWORD}
    ).status_code == 200


def test_unknown_user_is_404(admin):
    assert admin.put(f"{P}/api/users/99/password", json={"password": "password-9"}).status_code == 404
    assert admin.put(f"{P}/api/users/99/active", json={"is_active": False}).status_code == 404


def test_disabled_when_path_not_configured(anon_client, monkeypatch):
    import main
    monkeypatch.delenv("ADMIN_PATH")
    app = main.create_app()
    with TestClient(app) as c:
        assert c.get(f"{P}/").status_code == 404
        assert c.post(
            f"{P}/api/login", json={"username": "admin", "password": TEST_ADMIN_PASSWORD}
        ).status_code == 404


@pytest.mark.parametrize("bad", ["short", "has/slash-aaaaaaaaaaaa", "api"])
def test_invalid_admin_path_disables_admin(monkeypatch, bad):
    import admin as admin_module
    monkeypatch.setenv("ADMIN_PATH", bad)
    assert admin_module.configured_path() is None


def test_disabled_when_admin_password_never_set(anon_client):
    conn = accounts.connect()
    conn.execute("DELETE FROM admin")
    conn.commit()
    conn.close()
    assert anon_client.get(f"{P}/").status_code == 404
    assert admin_login(anon_client).status_code == 404
