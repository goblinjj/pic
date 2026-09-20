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
