import pytest


@pytest.fixture()
def category(client):
    return client.post("/api/categories", json={"name": "欢欢衣服"}).json()


def test_create_and_list_fields(client, category):
    r = client.post(
        f"/api/categories/{category['id']}/fields",
        json={"name": "品牌", "type": "select", "sort_order": 1},
    )
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == "品牌"
    assert created["type"] == "select"
    assert created["required"] is False
    assert created["show_in_list"] is False
    assert created["options"] == []

    listed = client.get(f"/api/categories/{category['id']}/fields").json()
    assert [f["id"] for f in listed] == [created["id"]]


def test_fields_are_ordered_by_sort_order(client, category):
    cid = category["id"]
    client.post(f"/api/categories/{cid}/fields", json={"name": "乙", "type": "text", "sort_order": 5})
    client.post(f"/api/categories/{cid}/fields", json={"name": "甲", "type": "text", "sort_order": 1})
    listed = client.get(f"/api/categories/{cid}/fields").json()
    assert [f["name"] for f in listed] == ["甲", "乙"]


def test_create_field_rejects_unknown_type(client, category):
    r = client.post(
        f"/api/categories/{category['id']}/fields",
        json={"name": "坏的", "type": "bogus"},
    )
    assert r.status_code == 400


def test_create_field_rejects_missing_category(client):
    r = client.post("/api/categories/99999/fields", json={"name": "x", "type": "text"})
    assert r.status_code == 404


def test_update_field_cannot_change_type(client, category):
    field = client.post(
        f"/api/categories/{category['id']}/fields",
        json={"name": "品牌", "type": "select"},
    ).json()
    r = client.put(f"/api/fields/{field['id']}", json={"name": "牌子", "type": "number"})
    assert r.status_code == 200
    assert r.json()["name"] == "牌子"
    assert r.json()["type"] == "select"


def test_update_field_toggles_flags(client, category):
    field = client.post(
        f"/api/categories/{category['id']}/fields",
        json={"name": "购入价格", "type": "number"},
    ).json()
    r = client.put(
        f"/api/fields/{field['id']}",
        json={"required": True, "show_in_list": True, "sort_order": 3},
    )
    body = r.json()
    assert body["required"] is True
    assert body["show_in_list"] is True
    assert body["sort_order"] == 3


def test_delete_field(client, category):
    field = client.post(
        f"/api/categories/{category['id']}/fields",
        json={"name": "临时", "type": "text"},
    ).json()
    assert client.delete(f"/api/fields/{field['id']}").status_code == 204
    assert client.get(f"/api/categories/{category['id']}/fields").json() == []


def test_delete_missing_field_returns_404(client):
    assert client.delete("/api/fields/99999").status_code == 404
