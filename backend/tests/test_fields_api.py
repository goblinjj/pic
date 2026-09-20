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


@pytest.fixture()
def select_field(client, category):
    return client.post(
        f"/api/categories/{category['id']}/fields",
        json={"name": "品牌", "type": "select"},
    ).json()


def test_create_option_and_read_back_on_field(client, category, select_field):
    r = client.post(f"/api/fields/{select_field['id']}/options", json={"label": "Nike"})
    assert r.status_code == 201
    assert r.json()["label"] == "Nike"

    fields = client.get(f"/api/categories/{category['id']}/fields").json()
    assert [o["label"] for o in fields[0]["options"]] == ["Nike"]


def test_options_are_ordered_by_sort_order(client, category, select_field):
    fid = select_field["id"]
    client.post(f"/api/fields/{fid}/options", json={"label": "乙", "sort_order": 5})
    client.post(f"/api/fields/{fid}/options", json={"label": "甲", "sort_order": 1})
    fields = client.get(f"/api/categories/{category['id']}/fields").json()
    assert [o["label"] for o in fields[0]["options"]] == ["甲", "乙"]


def test_option_rejected_on_non_option_field(client, category):
    text_field = client.post(
        f"/api/categories/{category['id']}/fields",
        json={"name": "备注", "type": "text"},
    ).json()
    r = client.post(f"/api/fields/{text_field['id']}/options", json={"label": "x"})
    assert r.status_code == 400


def test_rename_option(client, select_field):
    opt = client.post(f"/api/fields/{select_field['id']}/options", json={"label": "Nike"}).json()
    r = client.put(f"/api/options/{opt['id']}", json={"label": "NIKE"})
    assert r.status_code == 200
    assert r.json()["label"] == "NIKE"


def test_field_usage_counts_logs(client, category, select_field, db_conn):
    opt = client.post(f"/api/fields/{select_field['id']}/options", json={"label": "Nike"}).json()
    cur = db_conn.execute(
        "INSERT INTO logs (category_id, description) VALUES (?, '')", (category["id"],)
    )
    log_id = cur.lastrowid
    db_conn.execute(
        "INSERT INTO log_field_values (log_id, field_id, option_id) VALUES (?, ?, ?)",
        (log_id, select_field["id"], opt["id"]),
    )
    db_conn.commit()

    assert client.get(f"/api/fields/{select_field['id']}/usage").json()["log_count"] == 1
    assert client.get(f"/api/options/{opt['id']}/usage").json()["log_count"] == 1


def test_field_usage_counts_distinct_logs_not_rows(client, category, db_conn):
    # Create multiselect field with two options
    multiselect_field = client.post(
        f"/api/categories/{category['id']}/fields",
        json={"name": "颜色", "type": "multiselect"},
    ).json()
    opt1 = client.post(f"/api/fields/{multiselect_field['id']}/options", json={"label": "红"}).json()
    opt2 = client.post(f"/api/fields/{multiselect_field['id']}/options", json={"label": "蓝"}).json()

    # Insert one log with both options (two separate log_field_values rows)
    cur = db_conn.execute(
        "INSERT INTO logs (category_id, description) VALUES (?, '')", (category["id"],)
    )
    log_id_1 = cur.lastrowid
    db_conn.execute(
        "INSERT INTO log_field_values (log_id, field_id, option_id) VALUES (?, ?, ?)",
        (log_id_1, multiselect_field["id"], opt1["id"]),
    )
    db_conn.execute(
        "INSERT INTO log_field_values (log_id, field_id, option_id) VALUES (?, ?, ?)",
        (log_id_1, multiselect_field["id"], opt2["id"]),
    )
    db_conn.commit()

    # With one log having two rows, COUNT(DISTINCT log_id) should still be 1
    assert client.get(f"/api/fields/{multiselect_field['id']}/usage").json()["log_count"] == 1

    # Add a second log using the same field
    cur = db_conn.execute(
        "INSERT INTO logs (category_id, description) VALUES (?, '')", (category["id"],)
    )
    log_id_2 = cur.lastrowid
    db_conn.execute(
        "INSERT INTO log_field_values (log_id, field_id, option_id) VALUES (?, ?, ?)",
        (log_id_2, multiselect_field["id"], opt1["id"]),
    )
    db_conn.commit()

    # Now with two distinct logs, count should be 2
    assert client.get(f"/api/fields/{multiselect_field['id']}/usage").json()["log_count"] == 2


def test_deleting_field_cascades_to_options_and_values(client, category, select_field, db_conn):
    opt = client.post(f"/api/fields/{select_field['id']}/options", json={"label": "Nike"}).json()
    cur = db_conn.execute(
        "INSERT INTO logs (category_id, description) VALUES (?, '')", (category["id"],)
    )
    db_conn.execute(
        "INSERT INTO log_field_values (log_id, field_id, option_id) VALUES (?, ?, ?)",
        (cur.lastrowid, select_field["id"], opt["id"]),
    )
    db_conn.commit()

    assert client.delete(f"/api/fields/{select_field['id']}").status_code == 204
    assert db_conn.execute("SELECT id FROM field_options").fetchall() == []
    assert db_conn.execute("SELECT id FROM log_field_values").fetchall() == []


def test_deleting_option_cascades_to_values(client, category, select_field, db_conn):
    opt = client.post(f"/api/fields/{select_field['id']}/options", json={"label": "Nike"}).json()
    cur = db_conn.execute(
        "INSERT INTO logs (category_id, description) VALUES (?, '')", (category["id"],)
    )
    db_conn.execute(
        "INSERT INTO log_field_values (log_id, field_id, option_id) VALUES (?, ?, ?)",
        (cur.lastrowid, select_field["id"], opt["id"]),
    )
    db_conn.commit()

    assert client.delete(f"/api/options/{opt['id']}").status_code == 204
    assert db_conn.execute("SELECT id FROM log_field_values").fetchall() == []
