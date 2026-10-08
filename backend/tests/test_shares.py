"""主人侧分享管理：创建、列出、撤销，以及删除分类时联动。"""
import accounts


def _cat(client, name="手套"):
    return client.post("/api/categories", json={"name": name}).json()["id"]


def test_create_account_and_category_shares(client):
    cid = _cat(client)
    whole = client.post("/api/shares", json={"category_id": None})
    assert whole.status_code == 201, whole.text
    assert whole.json()["category_id"] is None
    assert whole.json()["category_name"] == ""
    assert len(whole.json()["token"]) == 32

    one = client.post("/api/shares", json={"category_id": cid}).json()
    assert (one["category_id"], one["category_name"]) == (cid, "手套")

    listed = client.get("/api/shares").json()
    assert [s["token"] for s in listed] == [one["token"], whole.json()["token"]]


def test_body_may_omit_category_id(client):
    resp = client.post("/api/shares", json={})
    assert resp.status_code == 201
    assert resp.json()["category_id"] is None


def test_create_with_unknown_category_400(client):
    resp = client.post("/api/shares", json={"category_id": 999})
    assert resp.status_code == 400
    assert client.get("/api/shares").json() == []


def test_list_only_own(client, make_user):
    client.post("/api/shares", json={})
    bob = make_user("bob")
    assert bob.get("/api/shares").json() == []


def test_revoke(client):
    token = client.post("/api/shares", json={}).json()["token"]
    assert client.delete(f"/api/shares/{token}").status_code == 204
    assert client.get("/api/shares").json() == []
    assert client.delete(f"/api/shares/{token}").status_code == 404


def test_cannot_revoke_others(client, make_user):
    token = client.post("/api/shares", json={}).json()["token"]
    bob = make_user("bob")
    assert bob.delete(f"/api/shares/{token}").status_code == 404
    assert len(client.get("/api/shares").json()) == 1


def test_deleting_category_removes_its_shares(client):
    keep = _cat(client, "保留")
    gone = _cat(client, "删除")
    t_keep = client.post("/api/shares", json={"category_id": keep}).json()["token"]
    client.post("/api/shares", json={"category_id": gone})
    t_all = client.post("/api/shares", json={}).json()["token"]

    assert client.delete(f"/api/categories/{gone}").status_code == 204
    assert {s["token"] for s in client.get("/api/shares").json()} == {t_keep, t_all}


def test_category_name_empty_when_category_missing(client):
    """分类直接从库里没了（比如手工改库）也照样列出，方便撤销。"""
    cid = _cat(client)
    conn = accounts.connect()
    accounts.create_share(conn, 1, cid + 100)
    conn.close()
    names = [s["category_name"] for s in client.get("/api/shares").json()]
    assert names == [""]


def test_requires_login(anon_client):
    assert anon_client.get("/api/shares").status_code == 401
    assert anon_client.post("/api/shares", json={}).status_code == 401
    assert anon_client.delete("/api/shares/x").status_code == 401
