import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "/app/data/piclog.db")


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            description TEXT DEFAULT '',
            external_link TEXT DEFAULT '',
            wire TEXT DEFAULT '',
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed')),
            deleted_at DATETIME DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );

        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (log_id) REFERENCES logs(id) ON DELETE CASCADE
        );
    """)
    # Migrate: add wire column if not exists
    cols = [row[1] for row in conn.execute("PRAGMA table_info(logs)").fetchall()]
    if "wire" not in cols:
        conn.execute("ALTER TABLE logs ADD COLUMN wire TEXT DEFAULT ''")
    if "deleted_at" not in cols:
        conn.execute("ALTER TABLE logs ADD COLUMN deleted_at DATETIME DEFAULT NULL")
    _init_custom_fields(conn)
    _run_one_time_migrations(conn)
    conn.commit()
    conn.close()


def _init_custom_fields(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS category_fields (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id  INTEGER NOT NULL,
            name         TEXT    NOT NULL,
            type         TEXT    NOT NULL
                         CHECK(type IN ('text','textarea','number','date','select','multiselect')),
            required     INTEGER NOT NULL DEFAULT 0,
            show_in_list INTEGER NOT NULL DEFAULT 0,
            sort_order   INTEGER NOT NULL DEFAULT 0,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS field_options (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            field_id   INTEGER NOT NULL,
            label      TEXT    NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (field_id) REFERENCES category_fields(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS log_field_values (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            log_id     INTEGER NOT NULL,
            field_id   INTEGER NOT NULL,
            value_text TEXT,
            value_num  REAL,
            value_date TEXT,
            option_id  INTEGER,
            FOREIGN KEY (log_id)    REFERENCES logs(id)            ON DELETE CASCADE,
            FOREIGN KEY (field_id)  REFERENCES category_fields(id) ON DELETE CASCADE,
            FOREIGN KEY (option_id) REFERENCES field_options(id)   ON DELETE CASCADE
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_lfv_uniq
            ON log_field_values(log_id, field_id, COALESCE(option_id, -1));
        CREATE INDEX IF NOT EXISTS idx_lfv_opt
            ON log_field_values(field_id, option_id);
        CREATE INDEX IF NOT EXISTS idx_lfv_num
            ON log_field_values(field_id, value_num);
        CREATE INDEX IF NOT EXISTS idx_lfv_date
            ON log_field_values(field_id, value_date);
    """)


GLOVE_CATEGORY_NAME = "手套"
WIRE_FIELD_NAME = "线材"

# 一次性迁移的版本号，记在库自身的 PRAGMA user_version 里。
# 1 = logs.wire 已迁移成「手套」分类下的「线材」自定义字段。
SCHEMA_VERSION = 1


def _run_one_time_migrations(conn):
    """按库里记录的版本号跑一次性迁移，跑过的永不重跑。

    关键：判断依据是版本号，不是「数据在不在」。用数据存在与否来判断的话，
    用户清空线材的值、或干脆删掉线材字段之后，下次启动又会被迁移重新写回来。
    全新空库没有「手套」分类，迁移是空操作，但一样要打上版本号，
    否则以后用户手工建了个叫「手套」的分类就会莫名其妙被迁移。
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    if version < 1:
        _migrate_wire_to_field(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _migrate_wire_to_field(conn):
    """把 logs.wire 的值迁移为「手套」分类下的「线材」自定义字段值。

    只由 _run_one_time_migrations 在整个库的生命周期里调用一次。
    logs.wire 列保留不删。
    """
    cat = conn.execute(
        "SELECT id FROM categories WHERE name = ?", (GLOVE_CATEGORY_NAME,)
    ).fetchone()
    if not cat:
        # 全新部署的空库没有任何分类，不凭空创建
        return
    category_id = cat[0]

    field = conn.execute(
        "SELECT id FROM category_fields WHERE category_id = ? AND name = ?",
        (category_id, WIRE_FIELD_NAME),
    ).fetchone()
    if field:
        field_id = field[0]
    else:
        cur = conn.execute(
            "INSERT INTO category_fields "
            "(category_id, name, type, required, show_in_list, sort_order) "
            "VALUES (?, ?, 'text', 0, 0, 0)",
            (category_id, WIRE_FIELD_NAME),
        )
        field_id = cur.lastrowid

    # 只迁移「手套」分类下的日志：线材字段只属于手套，
    # 给别的分类的日志写入这个 field_id 会破坏数据一致性
    conn.execute(
        """
        INSERT INTO log_field_values (log_id, field_id, value_text)
        SELECT l.id, ?, l.wire
        FROM logs l
        WHERE l.category_id = ?
          AND COALESCE(l.wire, '') <> ''
          AND NOT EXISTS (
              SELECT 1 FROM log_field_values v
              WHERE v.log_id = l.id AND v.field_id = ?
          )
        """,
        (field_id, category_id, field_id),
    )
