import pytest

import indexer
from tests.helpers import RED, solid_image_bytes


@pytest.fixture(autouse=True)
def clean_indexer_state():
    indexer.reset_state()
    yield
    indexer.reset_state()


@pytest.fixture()
def alice_data(client):
    """1 号账号的一套数据：分类、select 字段与选项、带图日志。"""
    cid = client.post("/api/categories", json={"name": "手套"}).json()["id"]
    field = client.post(
        f"/api/categories/{cid}/fields", json={"name": "颜色", "type": "select"}
    ).json()
    option = client.post(f"/api/fields/{field['id']}/options", json={"label": "红"}).json()
    log = client.post(
        "/api/logs",
        data={"category_id": cid, "description": "alice 的手套"},
        files=[("files", ("a.png", solid_image_bytes(RED), "image/png"))],
    ).json()
    return {"cid": cid, "fid": field["id"], "oid": option["id"], "log": log, "image": log["images"][0]}


def _bob_attempts(bob, data):
    lid, cid, fid, oid = data["log"]["id"], data["cid"], data["fid"], data["oid"]
    iid, fname = data["image"]["id"], data["image"]["filename"]
    return [
        bob.get(f"/api/logs/{lid}"),
        bob.put(f"/api/logs/{lid}", json={"description": "hacked"}),
        bob.patch(f"/api/logs/{lid}/status", json={"status": "completed"}),
        bob.delete(f"/api/logs/{lid}"),
        bob.put(f"/api/categories/{cid}", json={"name": "hacked"}),
        bob.delete(f"/api/categories/{cid}"),
        bob.get(f"/api/categories/{cid}/fields"),
        bob.put(f"/api/fields/{fid}", json={"name": "hacked"}),
        bob.delete(f"/api/fields/{fid}"),
        bob.put(f"/api/options/{oid}", json={"label": "hacked"}),
        bob.delete(f"/api/options/{oid}"),
        bob.delete(f"/api/images/{iid}"),
        bob.get(f"/api/files/{fname}"),
        bob.get(f"/api/files/thumbs/{fname}"),
    ]


def test_other_user_sees_empty_lists(alice_data, make_user):
    bob = make_user("bob")
    assert bob.get("/api/categories").json() == []
    assert bob.get("/api/logs").json()["total"] == 0


def test_other_user_cannot_read_or_change_by_id(alice_data, make_user):
    bob = make_user("bob")
    for resp in _bob_attempts(bob, alice_data):
        # 字段列表接口对不存在的分类可能返回 []，其余一律 404；
        # 关键是不能 2xx 且带着 alice 的数据
        assert resp.status_code in (404, 400) or resp.json() == [], (
            resp.request.url, resp.status_code, resp.text,
        )


def test_alice_data_untouched_after_bob_attempts(client, alice_data, make_user):
    _bob_attempts(make_user("bob"), alice_data)
    log = client.get(f"/api/logs/{alice_data['log']['id']}").json()
    assert log["description"] == "alice 的手套"
    assert log["status"] == "pending"
    assert len(log["images"]) == 1
    assert client.get(f"/api/files/{alice_data['image']['filename']}").status_code == 200
    assert [c["name"] for c in client.get("/api/categories").json()] == ["手套"]


def test_bob_cannot_upload_into_alice_log(alice_data, make_user):
    bob = make_user("bob")
    resp = bob.post(
        f"/api/logs/{alice_data['log']['id']}/images",
        files=[("files", ("x.png", solid_image_bytes(RED), "image/png"))],
    )
    assert resp.status_code == 404


def test_same_ids_in_both_accounts_stay_separate(client, make_user):
    """两个库的自增 id 都从 1 开始：同一个 id 在各自账号里指向各自的数据。"""
    bob = make_user("bob")
    a = client.post("/api/categories", json={"name": "alice-cat"}).json()
    b = bob.post("/api/categories", json={"name": "bob-cat"}).json()
    assert a["id"] == b["id"] == 1
    assert [c["name"] for c in client.get("/api/categories").json()] == ["alice-cat"]
    assert [c["name"] for c in bob.get("/api/categories").json()] == ["bob-cat"]


def test_image_search_only_returns_own_logs(client, fake_embedder, alice_data, make_user):
    bob = make_user("bob")
    indexer.process_pending()
    resp = bob.post(
        "/api/search/image",
        files={"file": ("q.png", solid_image_bytes(RED), "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["indexed"] == 0

    mine = client.post(
        "/api/search/image",
        files={"file": ("q.png", solid_image_bytes(RED), "image/png")},
    ).json()
    assert [h["log"]["id"] for h in mine["items"]] == [alice_data["log"]["id"]]
