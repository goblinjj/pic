import json

import pytest


@pytest.fixture()
def category(client):
    return client.post("/api/categories", json={"name": "欢欢衣服"}).json()


@pytest.fixture()
def fields(client, category):
    """建齐 6 种类型的字段，返回 {类型名: 字段 dict}。select/multiselect 各带两个选项。"""
    cid = category["id"]
    made = {}
    for order, (name, ftype) in enumerate([
        ("备注", "text"),
        ("详细描述", "textarea"),
        ("购入价格", "number"),
        ("购入日期", "date"),
        ("品牌", "select"),
        ("衣服类型", "multiselect"),
    ]):
        made[ftype] = client.post(
            f"/api/categories/{cid}/fields",
            json={"name": name, "type": ftype, "sort_order": order},
        ).json()

    for ftype, labels in (("select", ["Nike", "Adidas"]),
                          ("multiselect", ["外套", "卫衣"])):
        made[ftype]["options"] = [
            client.post(
                f"/api/fields/{made[ftype]['id']}/options", json={"label": label}
            ).json()
            for label in labels
        ]
    return made


def _write_value(db_conn, log_id, field, column, value):
    db_conn.execute(
        f"INSERT INTO log_field_values (log_id, field_id, {column}) VALUES (?, ?, ?)",
        (log_id, field["id"], value),
    )
    db_conn.commit()


def _make_log(client, category):
    return client.post(
        "/api/logs", data={"category_id": category["id"], "description": "一件衣服"}
    ).json()


def test_detail_returns_scalar_values(client, category, fields, db_conn):
    log = _make_log(client, category)
    _write_value(db_conn, log["id"], fields["text"], "value_text", "手写备注")
    _write_value(db_conn, log["id"], fields["number"], "value_num", 899.0)
    _write_value(db_conn, log["id"], fields["date"], "value_date", "2026-03-01")

    body = client.get(f"/api/logs/{log['id']}").json()
    by_name = {fv["name"]: fv for fv in body["field_values"]}
    assert by_name["备注"]["value"] == "手写备注"
    assert by_name["购入价格"]["value"] == 899.0
    assert by_name["购入日期"]["value"] == "2026-03-01"


def test_detail_returns_select_as_option_id_with_label(client, category, fields, db_conn):
    log = _make_log(client, category)
    nike = fields["select"]["options"][0]
    _write_value(db_conn, log["id"], fields["select"], "option_id", nike["id"])

    body = client.get(f"/api/logs/{log['id']}").json()
    brand = next(fv for fv in body["field_values"] if fv["name"] == "品牌")
    assert brand["value"] == nike["id"]
    assert brand["option_labels"] == ["Nike"]


def test_detail_returns_multiselect_as_list(client, category, fields, db_conn):
    log = _make_log(client, category)
    for opt in fields["multiselect"]["options"]:
        db_conn.execute(
            "INSERT INTO log_field_values (log_id, field_id, option_id) VALUES (?, ?, ?)",
            (log["id"], fields["multiselect"]["id"], opt["id"]),
        )
    db_conn.commit()

    body = client.get(f"/api/logs/{log['id']}").json()
    kind = next(fv for fv in body["field_values"] if fv["name"] == "衣服类型")
    assert kind["value"] == [o["id"] for o in fields["multiselect"]["options"]]
    assert kind["option_labels"] == ["外套", "卫衣"]


def test_renaming_option_changes_what_the_log_shows(client, category, fields, db_conn):
    log = _make_log(client, category)
    nike = fields["select"]["options"][0]
    _write_value(db_conn, log["id"], fields["select"], "option_id", nike["id"])

    client.put(f"/api/options/{nike['id']}", json={"label": "NIKE"})

    body = client.get(f"/api/logs/{log['id']}").json()
    brand = next(fv for fv in body["field_values"] if fv["name"] == "品牌")
    assert brand["option_labels"] == ["NIKE"]


def test_field_values_are_ordered_by_sort_order(client, category, fields, db_conn):
    log = _make_log(client, category)
    _write_value(db_conn, log["id"], fields["date"], "value_date", "2026-03-01")
    _write_value(db_conn, log["id"], fields["text"], "value_text", "备注内容")

    body = client.get(f"/api/logs/{log['id']}").json()
    assert [fv["name"] for fv in body["field_values"]] == ["备注", "购入日期"]


def test_log_without_values_returns_empty_list_while_sibling_log_does_not(
    client, category, fields, db_conn
):
    empty_log = _make_log(client, category)
    filled_log = _make_log(client, category)
    _write_value(db_conn, filled_log["id"], fields["text"], "value_text", "手写备注")

    empty_body = client.get(f"/api/logs/{empty_log['id']}").json()
    filled_body = client.get(f"/api/logs/{filled_log['id']}").json()

    assert empty_body["field_values"] == []
    by_name = {fv["name"]: fv for fv in filled_body["field_values"]}
    assert by_name["备注"]["value"] == "手写备注"


def test_create_log_with_field_values(client, category, fields):
    nike = fields["select"]["options"][0]
    coat = fields["multiselect"]["options"][0]
    payload = {
        str(fields["text"]["id"]): "备注内容",
        str(fields["number"]["id"]): 899,
        str(fields["date"]["id"]): "2026-03-01",
        str(fields["select"]["id"]): nike["id"],
        str(fields["multiselect"]["id"]): [coat["id"]],
    }
    log = client.post(
        "/api/logs",
        data={
            "category_id": category["id"],
            "description": "新衣服",
            "field_values": json.dumps(payload),
        },
    ).json()

    by_name = {fv["name"]: fv for fv in log["field_values"]}
    assert by_name["备注"]["value"] == "备注内容"
    assert by_name["购入价格"]["value"] == 899.0
    assert by_name["购入日期"]["value"] == "2026-03-01"
    assert by_name["品牌"]["option_labels"] == ["Nike"]
    assert by_name["衣服类型"]["option_labels"] == ["外套"]


def test_update_log_replaces_field_values(client, category, fields):
    log = client.post(
        "/api/logs",
        data={
            "category_id": category["id"],
            "description": "x",
            "field_values": json.dumps({str(fields["text"]["id"]): "旧值"}),
        },
    ).json()

    updated = client.put(
        f"/api/logs/{log['id']}",
        json={"field_values": {str(fields["text"]["id"]): "新值"}},
    ).json()

    notes = [fv for fv in updated["field_values"] if fv["name"] == "备注"]
    assert len(notes) == 1
    assert notes[0]["value"] == "新值"


def test_multiselect_replace_does_not_leave_stale_rows(client, category, fields, db_conn):
    coat, hoodie = fields["multiselect"]["options"]
    mid = fields["multiselect"]["id"]
    log = client.post(
        "/api/logs",
        data={
            "category_id": category["id"],
            "description": "x",
            "field_values": json.dumps({str(mid): [coat["id"], hoodie["id"]]}),
        },
    ).json()

    client.put(f"/api/logs/{log['id']}", json={"field_values": {str(mid): [hoodie["id"]]}})

    rows = db_conn.execute(
        "SELECT option_id FROM log_field_values WHERE log_id = ? AND field_id = ?",
        (log["id"], mid),
    ).fetchall()
    assert [r["option_id"] for r in rows] == [hoodie["id"]]


def test_duplicate_multiselect_options_are_deduped(client, category, fields, db_conn):
    coat = fields["multiselect"]["options"][0]
    mid = fields["multiselect"]["id"]
    log = client.post(
        "/api/logs",
        data={
            "category_id": category["id"],
            "description": "x",
            "field_values": json.dumps({str(mid): [coat["id"], coat["id"]]}),
        },
    ).json()

    rows = db_conn.execute(
        "SELECT id FROM log_field_values WHERE log_id = ? AND field_id = ?",
        (log["id"], mid),
    ).fetchall()
    assert len(rows) == 1


def test_required_field_rejects_empty_value(client, category, fields):
    client.put(f"/api/fields/{fields['text']['id']}", json={"required": True})
    r = client.post(
        "/api/logs",
        data={
            "category_id": category["id"],
            "description": "x",
            "field_values": json.dumps({str(fields["text"]["id"]): ""}),
        },
    )
    assert r.status_code == 400
    assert "必填" in r.json()["detail"]


def test_field_from_another_category_is_rejected(client, category, fields):
    other = client.post("/api/categories", json={"name": "手套"}).json()
    foreign = client.post(
        f"/api/categories/{other['id']}/fields", json={"name": "线材", "type": "text"}
    ).json()

    r = client.post(
        "/api/logs",
        data={
            "category_id": category["id"],
            "description": "x",
            "field_values": json.dumps({str(foreign["id"]): "尼龙线"}),
        },
    )
    assert r.status_code == 400


def test_number_field_rejects_non_numeric(client, category, fields):
    r = client.post(
        "/api/logs",
        data={
            "category_id": category["id"],
            "description": "x",
            "field_values": json.dumps({str(fields["number"]["id"]): "不是数字"}),
        },
    )
    assert r.status_code == 400


def test_empty_value_clears_the_field(client, category, fields):
    fid = fields["text"]["id"]
    log = client.post(
        "/api/logs",
        data={
            "category_id": category["id"],
            "description": "x",
            "field_values": json.dumps({str(fid): "有值"}),
        },
    ).json()

    updated = client.put(f"/api/logs/{log['id']}", json={"field_values": {str(fid): ""}}).json()
    assert updated["field_values"] == []
