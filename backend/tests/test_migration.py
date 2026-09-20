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
    """造一个「还没跑过本分支迁移」的旧库：有手套分类和带 wire 的日志。

    client fixture 起服务时已经跑过一次 init_db()，会把 user_version 打上标记；
    这里把它抹回 0，才能模拟真实 NAS 上那个从未跑过这段代码的库。
    """
    cur = db_conn.execute("INSERT INTO categories (name) VALUES ('手套')")
    cat_id = cur.lastrowid
    cur = db_conn.execute(
        "INSERT INTO logs (category_id, description, wire) VALUES (?, '旧日志', ?)",
        (cat_id, wire),
    )
    db_conn.execute("PRAGMA user_version = 0")
    db_conn.commit()
    return cat_id, cur.lastrowid


def _wire_field_id(db_conn, cat_id):
    row = db_conn.execute(
        "SELECT id FROM category_fields WHERE category_id = ? AND name = '线材'",
        (cat_id,),
    ).fetchone()
    return row["id"] if row else None


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


def test_cleared_wire_value_stays_cleared_across_restarts(client, db_conn):
    """用户在编辑页清空线材 → 重启不能把旧值再写回来。"""
    cat_id, log_id = _seed_glove_log_with_wire(db_conn)
    database.init_db()
    field_id = _wire_field_id(db_conn, cat_id)
    assert field_id is not None

    # 模拟用户清空该字段（save_field_values 清空就是删掉值行，不留空行）
    db_conn.execute(
        "DELETE FROM log_field_values WHERE log_id = ? AND field_id = ?",
        (log_id, field_id),
    )
    db_conn.commit()

    database.init_db()  # 下一次启动

    values = db_conn.execute(
        "SELECT id FROM log_field_values WHERE log_id = ? AND field_id = ?",
        (log_id, field_id),
    ).fetchall()
    assert values == [], "重启把用户清空的线材值又迁移回来了"


def test_deleted_wire_field_stays_deleted_across_restarts(client, db_conn):
    """用户在字段管理里删掉线材字段 → 重启不能把字段和值再造回来。"""
    cat_id, log_id = _seed_glove_log_with_wire(db_conn)
    database.init_db()
    field_id = _wire_field_id(db_conn, cat_id)
    assert field_id is not None

    db_conn.execute("DELETE FROM category_fields WHERE id = ?", (field_id,))
    db_conn.commit()

    database.init_db()  # 下一次启动

    fields = db_conn.execute(
        "SELECT id FROM category_fields WHERE category_id = ? AND name = '线材'",
        (cat_id,),
    ).fetchall()
    assert fields == [], "重启把用户删掉的线材字段又建回来了"

    values = db_conn.execute(
        "SELECT id FROM log_field_values WHERE log_id = ?", (log_id,)
    ).fetchall()
    assert values == []


def test_empty_new_database_is_marked_so_migration_never_lurks(client, db_conn):
    """全新空库没有手套分类，但也必须被标记成已迁移。"""
    assert db_conn.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION

    # 用户后来自己建了个叫「手套」的分类，并且某条日志的 wire 列有值
    cat = client.post("/api/categories", json={"name": "手套"}).json()
    db_conn.execute(
        "INSERT INTO logs (category_id, description, wire) VALUES (?, '新日志', '不该被迁移')",
        (cat["id"],),
    )
    db_conn.commit()

    database.init_db()

    fields = db_conn.execute(
        "SELECT id FROM category_fields WHERE category_id = ?", (cat["id"],)
    ).fetchall()
    assert fields == [], "迁移在新库里潜伏，等到出现同名分类才发作"
