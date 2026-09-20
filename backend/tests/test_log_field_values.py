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


def test_log_without_values_returns_empty_list(client, category, fields):
    log = _make_log(client, category)
    assert client.get(f"/api/logs/{log['id']}").json()["field_values"] == []
