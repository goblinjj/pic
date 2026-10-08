"""访客侧分享接口：不登录能读，且严格限定在分享范围内。"""
import os

import pytest
from fastapi.testclient import TestClient

import accounts
import indexer
import storage
import thumbnail
from main import app
from tests.helpers import BLUE, RED, solid_image_bytes


@pytest.fixture(autouse=True)
def clean_indexer_state():
    indexer.reset_state()
    yield
    indexer.reset_state()


def _log(client, cid, desc, color=RED, **extra):
    resp = client.post(
        "/api/logs",
        data={"category_id": cid, "description": desc, **extra},
        files=[("files", ("a.png", solid_image_bytes(color), "image/png"))],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def data(client):
    """1 号账号：手套（带 select 字段）两条、帽子一条、手套里一条已删除。"""
    gloves = client.post("/api/categories", json={"name": "手套"}).json()["id"]
    hats = client.post("/api/categories", json={"name": "帽子"}).json()["id"]
    field = client.post(
        f"/api/categories/{gloves}/fields", json={"name": "颜色", "type": "select"}
    ).json()
    client.post(f"/api/fields/{field['id']}/options", json={"label": "红"})
    g1 = _log(client, gloves, "红手套")
    g2 = _log(client, gloves, "蓝手套", BLUE)
    h1 = _log(client, hats, "红帽子")
    gone = _log(client, gloves, "已删")
    assert client.delete(f"/api/logs/{gone['id']}").status_code == 204
    return {"gloves": gloves, "hats": hats, "fid": field["id"],
            "g1": g1, "g2": g2, "h1": h1, "gone": gone}


@pytest.fixture()
def visitor():
    # 新 TestClient 没有任何 Cookie；不用 with，不重复触发 startup
    return TestClient(app)


def _share(client, category_id=None):
    resp = client.post("/api/shares", json={"category_id": category_id})
    assert resp.status_code == 201, resp.text
    return f"/api/share/{resp.json()['token']}"


def _fname(log):
    return log["images"][0]["filename"]


# ------------------------------------------------------------------ 账号级

def test_account_share_readable_without_login(client, data, visitor):
    base = _share(client)
    info = visitor.get(f"{base}/info").json()
    assert info == {"scope": "account", "category_id": None, "category_name": "", "owner": "babelingz"}

    assert [c["name"] for c in visitor.get(f"{base}/categories").json()] == ["手套", "帽子"]
    logs = visitor.get(f"{base}/logs").json()
    assert logs["total"] == 3
    assert {l["id"] for l in logs["items"]} == {data["g1"]["id"], data["g2"]["id"], data["h1"]["id"]}

    by_cat = visitor.get(f"{base}/logs", params={"category_id": data["hats"]}).json()
    assert [l["id"] for l in by_cat["items"]] == [data["h1"]["id"]]
    assert visitor.get(f"{base}/logs", params={"search": "蓝"}).json()["total"] == 1

    assert visitor.get(f"{base}/logs/{data['h1']['id']}").json()["description"] == "红帽子"
    assert len(visitor.get(f"{base}/categories/{data['gloves']}/fields").json()) == 1
    assert visitor.get(f"{base}/files/{_fname(data['h1'])}").status_code == 200
    assert visitor.get(f"{base}/files/thumbs/{_fname(data['h1'])}").status_code == 200


def test_deleted_log_hidden(client, data, visitor):
    base = _share(client)
    assert visitor.get(f"{base}/logs/{data['gone']['id']}").status_code == 404
    assert visitor.get(f"{base}/files/{_fname(data['gone'])}").status_code == 404
    assert visitor.get(f"{base}/files/thumbs/{_fname(data['gone'])}").status_code == 404


# ------------------------------------------------------------------ 分类级

def test_category_share_confined(client, data, visitor):
    base = _share(client, data["gloves"])
    info = visitor.get(f"{base}/info").json()
    assert info == {"scope": "category", "category_id": data["gloves"],
                    "category_name": "手套", "owner": "babelingz"}

    assert [c["name"] for c in visitor.get(f"{base}/categories").json()] == ["手套"]
    assert visitor.get(f"{base}/logs").json()["total"] == 2
    # 显式要别的分类：与范围 AND，结果为空
    assert visitor.get(f"{base}/logs", params={"category_id": data["hats"]}).json()["total"] == 0

    hat = data["h1"]
    assert visitor.get(f"{base}/logs/{hat['id']}").status_code == 404
    assert visitor.get(f"{base}/files/{_fname(hat)}").status_code == 404
    assert visitor.get(f"{base}/files/thumbs/{_fname(hat)}").status_code == 404
    assert visitor.get(f"{base}/categories/{data['hats']}/fields").status_code == 404
    assert visitor.get(f"{base}/categories/{data['gloves']}/fields").status_code == 200


def test_info_reflects_category_rename(client, data, visitor):
    base = _share(client, data["gloves"])
    client.put(f"/api/categories/{data['gloves']}", json={"name": "冬季手套"})
    assert visitor.get(f"{base}/info").json()["category_name"] == "冬季手套"


# ------------------------------------------------------------------ 失效

def _all_gets(visitor, base, data):
    f = _fname(data["g1"])
    return [
        visitor.get(f"{base}/info"),
        visitor.get(f"{base}/categories"),
        visitor.get(f"{base}/categories/{data['gloves']}/fields"),
        visitor.get(f"{base}/logs"),
        visitor.get(f"{base}/logs/{data['g1']['id']}"),
        visitor.get(f"{base}/files/{f}"),
        visitor.get(f"{base}/files/thumbs/{f}"),
        # 分享校验在嵌入模型检查之前，所以无需 fake_embedder 也应是统一的 404
        _search(visitor, base),
    ]


def _assert_all_404(responses):
    for r in responses:
        assert r.status_code == 404, (r.request.url, r.status_code, r.text)
        assert r.json()["detail"] == "分享链接不存在或已失效"


def test_unknown_token_404(data, visitor):
    _assert_all_404(_all_gets(visitor, "/api/share/nope", data))
    _assert_all_404(_all_gets(visitor, "/api/share/" + "x" * 300, data))


def test_revoked_404(client, data, visitor):
    base = _share(client)
    client.delete(f"/api/shares/{base.rsplit('/', 1)[1]}")
    _assert_all_404(_all_gets(visitor, base, data))


def test_disabled_then_reenabled_account(client, data, visitor):
    base = _share(client)
    conn = accounts.connect()
    accounts.set_active(conn, 1, False)
    _assert_all_404(_all_gets(visitor, base, data))
    accounts.set_active(conn, 1, True)
    conn.close()
    assert visitor.get(f"{base}/logs").json()["total"] == 3


def test_category_gone_404(client, data, visitor):
    cid = client.post("/api/categories", json={"name": "空"}).json()["id"]
    base = _share(client, cid)
    # 删分类本应连分享一起删；这里绕开它，模拟漏删的旧数据
    token = base.rsplit("/", 1)[1]
    conn = accounts.connect()
    conn.execute("DELETE FROM shares WHERE token = ?", (token,))
    conn.execute("INSERT INTO shares (token, user_id, category_id) VALUES (?, 1, ?)", (token, cid + 50))
    conn.commit()
    conn.close()
    _assert_all_404(_all_gets(visitor, base, data))


def test_missing_db_file_404(client, data, visitor):
    base = _share(client)
    path = storage.user_db_path(1)
    moved = path + ".moved"
    os.rename(path, moved)
    try:
        _assert_all_404([visitor.get(f"{base}/info")])
    finally:
        os.rename(moved, path)
    assert visitor.get(f"{base}/info").status_code == 200


# ------------------------------------------------------------------ 越权与边界

def test_other_account_token_cannot_reach_same_ids(client, data, make_user, visitor):
    bob = make_user("bob")
    cid = bob.post("/api/categories", json={"name": "bob 的"}).json()["id"]
    base = _share(bob)
    # bob 库里没有这些 id 的日志和文件
    assert visitor.get(f"{base}/logs").json()["total"] == 0
    assert visitor.get(f"{base}/logs/{data['g1']['id']}").status_code == 404
    assert visitor.get(f"{base}/files/{_fname(data['g1'])}").status_code == 404
    assert cid == data["gloves"]  # 两个账号的分类 id 撞号，确认隔离不靠 id


def test_other_account_cookie_does_not_matter(client, data, make_user):
    base = _share(client, data["gloves"])
    bob = make_user("bob")
    logs = bob.get(f"{base}/logs").json()
    assert {l["id"] for l in logs["items"]} == {data["g1"]["id"], data["g2"]["id"]}
    # 带着别的账号名的请求头也不影响（分享接口不认会话）
    resp = bob.get(f"{base}/logs", headers={"X-PicLog-User": "nobody"})
    assert resp.status_code == 200


def test_file_path_traversal_404(client, data, visitor):
    base = _share(client)
    # 带 %2F 的名字在路由层就被拒；只有 %2E%2E 会真正进到处理函数
    for name in ("..%2F..%2Fdata%2Fusers%2F1%2Fpiclog.db", "..%2Fpiclog.db", "%2E%2E"):
        assert visitor.get(f"{base}/files/{name}").status_code == 404
        assert visitor.get(f"{base}/files/thumbs/{name}").status_code == 404
    assert visitor.get(f"{base}/files/%2E%2E").json()["detail"] == "File not found"
    assert visitor.get(f"{base}/files/thumbs/%2E%2E").json()["detail"] == "File not found"


def test_unregistered_file_404(client, data, visitor):
    base = _share(client)
    upload_dir = storage.user_upload_dir(1)
    thumbs = thumbnail.thumb_dir(upload_dir)
    os.makedirs(thumbs, exist_ok=True)
    for d in (upload_dir, thumbs):
        with open(os.path.join(d, "stray.png"), "wb") as f:
            f.write(solid_image_bytes(RED))
    try:
        for url in (f"{base}/files/stray.png", f"{base}/files/thumbs/stray.png"):
            r = visitor.get(url)
            assert r.status_code == 404 and r.json()["detail"] == "File not found"
        # 对照：登记过的文件仍可读
        assert visitor.get(f"{base}/files/{_fname(data['g1'])}").status_code == 200
    finally:
        for d in (upload_dir, thumbs):
            os.remove(os.path.join(d, "stray.png"))


def test_logs_page_and_size_bounds(client, data, visitor):
    base = _share(client)
    assert visitor.get(f"{base}/logs", params={"size": 101}).status_code == 422
    assert visitor.get(f"{base}/logs", params={"size": 0}).status_code == 422
    assert visitor.get(f"{base}/logs", params={"page": 0}).status_code == 422
    assert visitor.get(f"{base}/logs", params={"page": 10**18}).status_code == 422
    assert visitor.get(f"{base}/logs", params={"size": 100}).status_code == 200


def test_no_write_methods(client, data, visitor):
    base = _share(client)
    lid, iid = data["g1"]["id"], data["g1"]["images"][0]["id"]
    attempts = [
        visitor.post(f"{base}/logs", data={"category_id": data["gloves"]}),
        visitor.put(f"{base}/logs/{lid}", json={"description": "hacked"}),
        visitor.patch(f"{base}/logs/{lid}/status", json={"status": "completed"}),
        visitor.delete(f"{base}/logs/{lid}"),
        visitor.post(f"{base}/logs/{lid}/images", files=[("files", ("x.png", b"x", "image/png"))]),
        visitor.delete(f"{base}/images/{iid}"),
        visitor.post(f"{base}/categories", json={"name": "x"}),
        visitor.delete(f"{base}/categories/{data['gloves']}"),
    ]
    for r in attempts:
        assert r.status_code in (404, 405), (r.request.method, r.request.url, r.status_code)
    log = client.get(f"/api/logs/{lid}").json()
    assert log["description"] == "红手套" and len(log["images"]) == 1

# ------------------------------------------------------------------ 以图搜图

def _search(c, base, color=RED):
    return c.post(f"{base}/search/image",
                  files={"file": ("q.png", solid_image_bytes(color), "image/png")})


def test_image_search_confined_to_category(client, data, visitor, fake_embedder):
    assert indexer.process_pending() == 3   # 已删除那条不建索引
    base = _share(client, data["gloves"])
    resp = _search(visitor, base)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = [it["log"]["id"] for it in body["items"]]
    assert ids == [data["g1"]["id"]]          # 红帽子在别的分类，不出现
    assert body["pending"] == 0
    assert body["indexed"] == 2


def test_image_search_account_scope(client, data, visitor, fake_embedder):
    indexer.process_pending()
    base = _share(client)
    ids = {it["log"]["id"] for it in _search(visitor, base).json()["items"]}
    assert ids == {data["g1"]["id"], data["h1"]["id"]}


def test_image_search_rate_limited(client, data, visitor, fake_embedder):
    base = _share(client)
    for _ in range(10):
        assert _search(visitor, base).status_code == 200
    resp = _search(visitor, base)
    assert resp.status_code == 429
    assert resp.json()["detail"] == "搜索太频繁，请稍后再试"


def test_image_search_bad_token_404(visitor):
    assert _search(visitor, "/api/share/nope").status_code == 404
