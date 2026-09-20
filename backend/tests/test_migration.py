import database


def test_custom_field_tables_exist(client, db_conn):
    names = {
        r["name"]
        for r in db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert "category_fields" in names
    assert "field_options" in names
    assert "log_field_values" in names


def test_field_type_check_constraint(client, db_conn):
    import sqlite3
    cat = client.post("/api/categories", json={"name": "手套"}).json()
    try:
        db_conn.execute(
            "INSERT INTO category_fields (category_id, name, type) VALUES (?, ?, ?)",
            (cat["id"], "坏类型", "bogus"),
        )
        db_conn.commit()
    except sqlite3.IntegrityError:
        return
    raise AssertionError("CHECK 约束没有拦住非法字段类型")


def test_scalar_value_is_unique_per_log_and_field(client, db_conn):
    import sqlite3
    cat = client.post("/api/categories", json={"name": "手套"}).json()
    cur = db_conn.execute(
        "INSERT INTO category_fields (category_id, name, type) VALUES (?, ?, 'text')",
        (cat["id"], "线材"),
    )
    field_id = cur.lastrowid
    cur = db_conn.execute(
        "INSERT INTO logs (category_id, description) VALUES (?, '')", (cat["id"],)
    )
    log_id = cur.lastrowid
    db_conn.execute(
        "INSERT INTO log_field_values (log_id, field_id, value_text) VALUES (?, ?, 'a')",
        (log_id, field_id),
    )
    db_conn.commit()
    try:
        db_conn.execute(
            "INSERT INTO log_field_values (log_id, field_id, value_text) VALUES (?, ?, 'b')",
            (log_id, field_id),
        )
        db_conn.commit()
    except sqlite3.IntegrityError:
        return
    raise AssertionError("唯一索引没有拦住标量字段的第二行值")


def _seed_glove_log_with_wire(db_conn, wire="尼龙线"):
    cur = db_conn.execute("INSERT INTO categories (name) VALUES ('手套')")
    cat_id = cur.lastrowid
    cur = db_conn.execute(
        "INSERT INTO logs (category_id, description, wire) VALUES (?, '旧日志', ?)",
        (cat_id, wire),
    )
    db_conn.commit()
    return cat_id, cur.lastrowid


def test_wire_migrates_into_glove_field(client, db_conn):
    cat_id, log_id = _seed_glove_log_with_wire(db_conn)
    database.init_db()

    field = db_conn.execute(
        "SELECT id, type, sort_order FROM category_fields "
        "WHERE category_id = ? AND name = '线材'",
        (cat_id,),
    ).fetchone()
    assert field is not None
    assert field["type"] == "text"

    value = db_conn.execute(
        "SELECT value_text FROM log_field_values WHERE log_id = ? AND field_id = ?",
        (log_id, field["id"]),
    ).fetchone()
    assert value["value_text"] == "尼龙线"


def test_wire_migration_is_idempotent(client, db_conn):
    cat_id, log_id = _seed_glove_log_with_wire(db_conn)
    database.init_db()
    database.init_db()
    database.init_db()

    fields = db_conn.execute(
        "SELECT id FROM category_fields WHERE category_id = ? AND name = '线材'",
        (cat_id,),
    ).fetchall()
    assert len(fields) == 1

    values = db_conn.execute(
        "SELECT id FROM log_field_values WHERE log_id = ?", (log_id,)
    ).fetchall()
    assert len(values) == 1


def test_migration_skips_when_no_glove_category(client, db_conn):
    client.post("/api/categories", json={"name": "欢欢衣服"})
    database.init_db()

    cats = db_conn.execute("SELECT name FROM categories").fetchall()
    assert [c["name"] for c in cats] == ["欢欢衣服"]

    fields = db_conn.execute("SELECT id FROM category_fields").fetchall()
    assert fields == []


def test_wire_outside_glove_category_is_not_migrated(client, db_conn):
    cat_id, _ = _seed_glove_log_with_wire(db_conn)
    cur = db_conn.execute("INSERT INTO categories (name) VALUES ('欢欢衣服')")
    other_id = cur.lastrowid
    cur = db_conn.execute(
        "INSERT INTO logs (category_id, description, wire) VALUES (?, '别的', '不该迁移')",
        (other_id,),
    )
    other_log_id = cur.lastrowid
    db_conn.commit()

    database.init_db()

    values = db_conn.execute(
        "SELECT id FROM log_field_values WHERE log_id = ?", (other_log_id,)
    ).fetchall()
    assert values == []
