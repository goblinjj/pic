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
    _migrate_wire_to_field(conn)
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


def _migrate_wire_to_field(conn):
    """把 logs.wire 的值迁移为「手套」分类下的「线材」自定义字段值。幂等。"""
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
