# 分类绑定自定义字段 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 PicLog 的日志字段从硬编码改为按分类配置的动态字段，支持 6 种类型、可自定义下拉选项、可筛选排序、可选择显示在列表卡片上。

**Architecture:** 三张新表构成 EAV 模型——`category_fields` 定义字段、`field_options` 定义下拉选项、`log_field_values` 按类型分列存值（`value_text`/`value_num`/`value_date`/`option_id`）。下拉值存 `option_id` 而非文本，因此重命名选项对历史日志自动生效。多选字段每个选中项存一行，由表达式唯一索引 `COALESCE(option_id, -1)` 同时约束标量字段的单行性与多选字段的不重复。后端新增 `field_values.py` 承载取值/存值/筛选/排序的 SQL 构造，新增 `routers/fields.py` 承载字段与选项的 CRUD，避免 `logs.py` 继续膨胀。

**Tech Stack:** FastAPI 0.115 / SQLite 3.46（容器内）/ Pydantic v2 / pytest + httpx（仅开发依赖）/ Vue 3 `<script setup>` / Vue Router 4 / Tailwind CSS v4 / Vite 5

**Spec:** `docs/superpowers/specs/2026-09-20-category-custom-fields-design.md`

## Global Constraints

- 字段类型固定为 6 种，字面量顺序统一为：`text`, `textarea`, `number`, `date`, `select`, `multiselect`
- 字段的 `type` 创建后不可修改；`CategoryFieldUpdate` 模型中**不得**包含 `type` 字段
- 下拉与多选的值一律存 `option_id`，**不存**标签文本
- `logs.wire` 列保留不删；本次改动后所有新代码**不读不写**该列
- 生产库现状：分类 `5 手套` / `6 欢欢衣服`；有效日志 1 条在「手套」下且填了线材；容器内 SQLite 3.46.1
- 不新增任何生产运行时依赖；`pytest`/`httpx` 只进 `backend/requirements-dev.txt`，不进 `backend/requirements.txt`，不进 Dockerfile
- 不引入前端测试框架，不引入拖拽排序库；排序一律用 `sort_order` 数字输入框
- 前端所有请求走相对路径（`api.js` 的 `BASE = ''`），不得出现任何绝对域名
- **Python 一律用 `backend/.venv/bin/`**（系统 python3 没装 fastapi）。环境已由
  `./scripts/setup-dev.sh` 配好；venv 是 Python 3.14.3，生产容器是 3.12，
  已实测 fastapi 0.115.0 + pydantic 2.13.5 在两者上行为一致
- 提交即可，**不要执行 `git push`** —— push 会触发 pre-push hook 部署到生产 NAS。
  部署由人在全部任务完成后手动发起
- 日期值一律用 `'YYYY-MM-DD'` 字符串
- 所有新建表与索引使用 `IF NOT EXISTS`，迁移必须幂等

## 文件结构

**新建**

| 文件 | 职责 |
| --- | --- |
| `backend/field_values.py` | 字段值的读取、写入、筛选/排序 SQL 构造。纯函数 + 接收 `sqlite3.Connection`，不依赖 FastAPI 路由 |
| `backend/routers/fields.py` | `category_fields` 与 `field_options` 的 CRUD、`usage` 端点 |
| `backend/requirements-dev.txt` | 测试依赖，不进生产镜像 |
| `backend/tests/conftest.py` | pytest fixture：临时 DB、TestClient、原始连接 |
| `backend/tests/test_migration.py` | 建表与 wire 迁移 |
| `backend/tests/test_fields_api.py` | 字段与选项 CRUD、usage、级联删除 |
| `backend/tests/test_log_field_values.py` | 日志字段值读写、必填校验 |
| `backend/tests/test_log_filter_sort.py` | 筛选语义与排序 |
| `frontend/src/views/CategoryFields.vue` | 字段管理子页 `/categories/:id/fields` |
| `frontend/src/components/DynamicField.vue` | 按字段定义渲染单个输入控件，`v-model` 出值 |

**修改**

| 文件 | 改动 |
| --- | --- |
| `backend/database.py` | 建三张新表 + wire 迁移 |
| `backend/models.py` | 新增字段/选项/字段值的 Pydantic 模型；`LogOut` 增 `field_values`、去 `wire`；`LogUpdate` 去 `wire` 增 `field_values` |
| `backend/main.py` | 注册 `fields` 路由 |
| `backend/routers/logs.py` | 读写字段值、筛选排序、列表批量加载 |
| `frontend/src/api.js` | 新增 9 个端点封装；`getLogs` 支持数组参数 |
| `frontend/src/router.js` | 新增 `/categories/:id/fields` 路由 |
| `frontend/src/views/Categories.vue` | 分类行增加进入字段管理的入口 |
| `frontend/src/views/LogForm.vue` | 移除线材输入框，改为动态字段渲染 |
| `frontend/src/views/LogDetail.vue` | 移除线材展示块，改为渲染 `field_values` |
| `frontend/src/views/LogList.vue` | 卡片展示 `show_in_list` 字段；筛选与排序控件 |

---

### Task 1: 测试基建与三张新表

**Files:**
- Create: `backend/requirements-dev.txt`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_migration.py`
- Modify: `backend/database.py`

**Interfaces:**
- Consumes: 无
- Produces: `database._init_custom_fields(conn: sqlite3.Connection) -> None`；pytest fixture `client`（`fastapi.testclient.TestClient`）与 `db_conn`（`sqlite3.Connection`，`row_factory` 已设为 `sqlite3.Row`）

- [ ] **Step 1: 建测试依赖文件**

`backend/requirements-dev.txt`：

```
-r requirements.txt
pytest==8.3.3
httpx==0.27.2
```

- [ ] **Step 2: 建 conftest**

`backend/tests/__init__.py` 留空。`backend/tests/conftest.py`：

```python
import os
import sys
import sqlite3
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# 必须在 import database / main 之前设置：两者在模块级读取这些环境变量
_TMP = tempfile.mkdtemp(prefix="piclog-test-")
os.environ["DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["UPLOAD_DIR"] = os.path.join(_TMP, "uploads")
# 指向不存在的目录，让 main.py 跳过 SPA catch-all 挂载，否则 404 会被兜底路由吞掉
os.environ["STATIC_DIR"] = os.path.join(_TMP, "no-static")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
from main import app  # noqa: E402


def _reset_db():
    for suffix in ("", "-wal", "-shm"):
        path = database.DB_PATH + suffix
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture()
def client():
    _reset_db()
    # TestClient 进入上下文时会触发 startup，startup 里会调 init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db_conn():
    conn = sqlite3.connect(database.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    yield conn
    conn.close()
```

- [ ] **Step 3: 写失败的测试**

`backend/tests/test_migration.py`：

```python
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
```

- [ ] **Step 4: 运行测试确认失败**

```bash
cd backend && .venv/bin/pytest tests/test_migration.py -v
```

预期：三个测试全部 FAIL（表不存在）。

- [ ] **Step 5: 在 database.py 中建表**

在 `backend/database.py` 末尾追加：

```python
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
```

在 `init_db()` 中、`conn.close()` 之前调用它——紧跟在现有 `deleted_at` 迁移之后：

```python
    if "deleted_at" not in cols:
        conn.execute("ALTER TABLE logs ADD COLUMN deleted_at DATETIME DEFAULT NULL")
    _init_custom_fields(conn)
    conn.commit()
    conn.close()
```

- [ ] **Step 6: 运行测试确认通过**

```bash
cd backend && .venv/bin/pytest tests/test_migration.py -v
```

预期：3 passed。

- [ ] **Step 7: 提交**

```bash
git add backend/requirements-dev.txt backend/tests backend/database.py
git commit -m "Add custom field tables and backend test harness"
```

---

### Task 2: wire 迁移为「手套」分类的「线材」字段

**Files:**
- Modify: `backend/database.py`
- Modify: `backend/tests/test_migration.py`

**Interfaces:**
- Consumes: `database._init_custom_fields`（Task 1）
- Produces: `database._migrate_wire_to_field(conn: sqlite3.Connection) -> None`

- [ ] **Step 1: 写失败的测试**

追加到 `backend/tests/test_migration.py`：

```python
import database


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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && .venv/bin/pytest tests/test_migration.py -v -k wire或migration_skips
```

实际命令：

```bash
cd backend && .venv/bin/pytest tests/test_migration.py -v
```

预期：4 个新测试 FAIL（`category_fields` 里没有「线材」）。

- [ ] **Step 3: 实现迁移**

在 `backend/database.py` 的 `_init_custom_fields` 之后追加：

```python
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
```

在 `init_db()` 里紧跟 `_init_custom_fields(conn)` 之后调用：

```python
    _init_custom_fields(conn)
    _migrate_wire_to_field(conn)
    conn.commit()
    conn.close()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && .venv/bin/pytest tests/test_migration.py -v
```

预期：7 passed。

- [ ] **Step 5: 提交**

```bash
git add backend/database.py backend/tests/test_migration.py
git commit -m "Migrate logs.wire into a custom field on the glove category"
```

---

### Task 3: Pydantic 模型

**Files:**
- Modify: `backend/models.py`

**Interfaces:**
- Consumes: 无
- Produces: `FIELD_TYPES: tuple[str, ...]`、`FieldOptionOut`、`FieldOptionCreate`、`FieldOptionUpdate`、`CategoryFieldCreate`、`CategoryFieldUpdate`、`CategoryFieldOut`、`FieldValueOut`、`UsageOut`；`LogOut.field_values: list[FieldValueOut]`；`LogUpdate.field_values: dict[str, Any] | None`

- [ ] **Step 1: 改 models.py**

把 `backend/models.py` 第 2 行的 import 改为：

```python
from typing import Any, Optional
```

在 `class StatusUpdate` 之前插入：

```python
FIELD_TYPES = ("text", "textarea", "number", "date", "select", "multiselect")
OPTION_TYPES = ("select", "multiselect")


class FieldOptionOut(BaseModel):
    id: int
    field_id: int
    label: str
    sort_order: int


class FieldOptionCreate(BaseModel):
    label: str
    sort_order: int = 0


class FieldOptionUpdate(BaseModel):
    label: Optional[str] = None
    sort_order: Optional[int] = None


class CategoryFieldCreate(BaseModel):
    name: str
    type: str
    required: bool = False
    show_in_list: bool = False
    sort_order: int = 0


class CategoryFieldUpdate(BaseModel):
    # 刻意不含 type：字段类型创建后不可修改，改类型会让已存的值落在错误的列上
    name: Optional[str] = None
    required: Optional[bool] = None
    show_in_list: Optional[bool] = None
    sort_order: Optional[int] = None


class CategoryFieldOut(BaseModel):
    id: int
    category_id: int
    name: str
    type: str
    required: bool
    show_in_list: bool
    sort_order: int
    options: list[FieldOptionOut] = []


class FieldValueOut(BaseModel):
    field_id: int
    name: str
    type: str
    sort_order: int
    show_in_list: bool
    value: Any = None          # 标量值 / select 的 option_id / multiselect 的 option_id 列表
    option_labels: list[str] = []


class UsageOut(BaseModel):
    log_count: int
```

把 `LogUpdate` 改为（去掉 `wire`，加上 `field_values`）：

```python
class LogUpdate(BaseModel):
    category_id: Optional[int] = None
    description: Optional[str] = None
    external_link: Optional[str] = None
    field_values: Optional[dict[str, Any]] = None
```

把 `LogOut` 改为（去掉 `wire`，加上 `field_values`）：

```python
class LogOut(BaseModel):
    id: int
    category_id: int
    category_name: str = ""
    description: str
    external_link: str
    status: str
    created_at: str
    updated_at: str
    images: list[ImageOut] = []
    field_values: list[FieldValueOut] = []
```

- [ ] **Step 2: 确认现有测试仍然通过**

```bash
cd backend && .venv/bin/pytest tests -v
```

预期：7 passed。（`logs.py` 此刻仍在 SELECT `wire`，但 `LogOut` 不再声明它，Pydantic 会忽略多余键。）

- [ ] **Step 3: 提交**

```bash
git add backend/models.py
git commit -m "Add pydantic models for custom fields, drop wire from log schemas"
```

---

### Task 4: 字段 CRUD API

**Files:**
- Create: `backend/routers/fields.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_fields_api.py`

**Interfaces:**
- Consumes: Task 3 的全部模型；`database.get_db`
- Produces: HTTP 端点 `GET|POST /api/categories/{cid}/fields`、`PUT|DELETE /api/fields/{fid}`；模块内函数 `_field_row_to_dict(db, row) -> dict`

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_fields_api.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && .venv/bin/pytest tests/test_fields_api.py -v
```

预期：全部 FAIL（404，路由不存在）。

- [ ] **Step 3: 实现路由**

`backend/routers/fields.py`：

```python
from fastapi import APIRouter, Depends, HTTPException
import sqlite3
from database import get_db
from models import (
    FIELD_TYPES,
    OPTION_TYPES,
    CategoryFieldCreate,
    CategoryFieldUpdate,
    CategoryFieldOut,
)

router = APIRouter(tags=["fields"])

FIELD_COLUMNS = (
    "id, category_id, name, type, required, show_in_list, sort_order"
)


def _field_row_to_dict(db: sqlite3.Connection, row) -> dict:
    field = dict(row)
    field["required"] = bool(field["required"])
    field["show_in_list"] = bool(field["show_in_list"])
    if field["type"] in OPTION_TYPES:
        opts = db.execute(
            "SELECT id, field_id, label, sort_order FROM field_options "
            "WHERE field_id = ? ORDER BY sort_order, id",
            (field["id"],),
        ).fetchall()
        field["options"] = [dict(o) for o in opts]
    else:
        field["options"] = []
    return field


def _get_field_or_404(db: sqlite3.Connection, field_id: int):
    row = db.execute(
        f"SELECT {FIELD_COLUMNS} FROM category_fields WHERE id = ?", (field_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Field not found")
    return row


@router.get("/api/categories/{category_id}/fields", response_model=list[CategoryFieldOut])
def list_fields(category_id: int, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        f"SELECT {FIELD_COLUMNS} FROM category_fields "
        "WHERE category_id = ? ORDER BY sort_order, id",
        (category_id,),
    ).fetchall()
    return [_field_row_to_dict(db, r) for r in rows]


@router.post(
    "/api/categories/{category_id}/fields",
    response_model=CategoryFieldOut,
    status_code=201,
)
def create_field(
    category_id: int,
    body: CategoryFieldCreate,
    db: sqlite3.Connection = Depends(get_db),
):
    cat = db.execute(
        "SELECT id FROM categories WHERE id = ?", (category_id,)
    ).fetchone()
    if not cat:
        raise HTTPException(404, "Category not found")
    if body.type not in FIELD_TYPES:
        raise HTTPException(400, f"Invalid field type: {body.type}")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "字段名称不能为空")

    cur = db.execute(
        "INSERT INTO category_fields "
        "(category_id, name, type, required, show_in_list, sort_order) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (category_id, name, body.type, int(body.required),
         int(body.show_in_list), body.sort_order),
    )
    db.commit()
    return _field_row_to_dict(db, _get_field_or_404(db, cur.lastrowid))


@router.put("/api/fields/{field_id}", response_model=CategoryFieldOut)
def update_field(
    field_id: int,
    body: CategoryFieldUpdate,
    db: sqlite3.Connection = Depends(get_db),
):
    _get_field_or_404(db, field_id)

    updates, params = [], []
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "字段名称不能为空")
        updates.append("name = ?")
        params.append(name)
    if body.required is not None:
        updates.append("required = ?")
        params.append(int(body.required))
    if body.show_in_list is not None:
        updates.append("show_in_list = ?")
        params.append(int(body.show_in_list))
    if body.sort_order is not None:
        updates.append("sort_order = ?")
        params.append(body.sort_order)

    if updates:
        params.append(field_id)
        db.execute(
            f"UPDATE category_fields SET {', '.join(updates)} WHERE id = ?", params
        )
        db.commit()

    return _field_row_to_dict(db, _get_field_or_404(db, field_id))


@router.delete("/api/fields/{field_id}", status_code=204)
def delete_field(field_id: int, db: sqlite3.Connection = Depends(get_db)):
    _get_field_or_404(db, field_id)
    db.execute("DELETE FROM category_fields WHERE id = ?", (field_id,))
    db.commit()
```

- [ ] **Step 4: 注册路由**

修改 `backend/main.py` 第 6 行与路由注册段：

```python
from routers import categories, logs, images, fields
```

```python
app.include_router(categories.router)
app.include_router(logs.router)
app.include_router(images.router)
app.include_router(fields.router)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && .venv/bin/pytest tests -v
```

预期：15 passed。

- [ ] **Step 6: 提交**

```bash
git add backend/routers/fields.py backend/main.py backend/tests/test_fields_api.py
git commit -m "Add CRUD API for category fields"
```

---

### Task 5: 选项 CRUD、usage 端点与级联删除

**Files:**
- Modify: `backend/routers/fields.py`
- Modify: `backend/tests/test_fields_api.py`

**Interfaces:**
- Consumes: Task 4 的 `_field_row_to_dict`、`_get_field_or_404`
- Produces: HTTP 端点 `POST /api/fields/{fid}/options`、`PUT|DELETE /api/options/{oid}`、`GET /api/fields/{fid}/usage`、`GET /api/options/{oid}/usage`

- [ ] **Step 1: 写失败的测试**

追加到 `backend/tests/test_fields_api.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && .venv/bin/pytest tests/test_fields_api.py -v
```

预期：7 个新测试 FAIL。

- [ ] **Step 3: 实现选项与 usage 端点**

`backend/routers/fields.py` 的 import 增加模型：

```python
from models import (
    FIELD_TYPES,
    OPTION_TYPES,
    CategoryFieldCreate,
    CategoryFieldUpdate,
    CategoryFieldOut,
    FieldOptionCreate,
    FieldOptionUpdate,
    FieldOptionOut,
    UsageOut,
)
```

文件末尾追加：

```python
def _get_option_or_404(db: sqlite3.Connection, option_id: int):
    row = db.execute(
        "SELECT id, field_id, label, sort_order FROM field_options WHERE id = ?",
        (option_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Option not found")
    return row


@router.post(
    "/api/fields/{field_id}/options", response_model=FieldOptionOut, status_code=201
)
def create_option(
    field_id: int,
    body: FieldOptionCreate,
    db: sqlite3.Connection = Depends(get_db),
):
    field = _get_field_or_404(db, field_id)
    if field["type"] not in OPTION_TYPES:
        raise HTTPException(400, "只有下拉/多选类型的字段才能配置选项")
    label = body.label.strip()
    if not label:
        raise HTTPException(400, "选项名称不能为空")

    cur = db.execute(
        "INSERT INTO field_options (field_id, label, sort_order) VALUES (?, ?, ?)",
        (field_id, label, body.sort_order),
    )
    db.commit()
    return dict(_get_option_or_404(db, cur.lastrowid))


@router.put("/api/options/{option_id}", response_model=FieldOptionOut)
def update_option(
    option_id: int,
    body: FieldOptionUpdate,
    db: sqlite3.Connection = Depends(get_db),
):
    _get_option_or_404(db, option_id)

    updates, params = [], []
    if body.label is not None:
        label = body.label.strip()
        if not label:
            raise HTTPException(400, "选项名称不能为空")
        updates.append("label = ?")
        params.append(label)
    if body.sort_order is not None:
        updates.append("sort_order = ?")
        params.append(body.sort_order)

    if updates:
        params.append(option_id)
        db.execute(
            f"UPDATE field_options SET {', '.join(updates)} WHERE id = ?", params
        )
        db.commit()

    return dict(_get_option_or_404(db, option_id))


@router.delete("/api/options/{option_id}", status_code=204)
def delete_option(option_id: int, db: sqlite3.Connection = Depends(get_db)):
    _get_option_or_404(db, option_id)
    db.execute("DELETE FROM field_options WHERE id = ?", (option_id,))
    db.commit()


@router.get("/api/fields/{field_id}/usage", response_model=UsageOut)
def field_usage(field_id: int, db: sqlite3.Connection = Depends(get_db)):
    _get_field_or_404(db, field_id)
    row = db.execute(
        "SELECT COUNT(DISTINCT log_id) AS c FROM log_field_values WHERE field_id = ?",
        (field_id,),
    ).fetchone()
    return {"log_count": row["c"]}


@router.get("/api/options/{option_id}/usage", response_model=UsageOut)
def option_usage(option_id: int, db: sqlite3.Connection = Depends(get_db)):
    _get_option_or_404(db, option_id)
    row = db.execute(
        "SELECT COUNT(DISTINCT log_id) AS c FROM log_field_values WHERE option_id = ?",
        (option_id,),
    ).fetchone()
    return {"log_count": row["c"]}
```

> 级联删除依赖 `PRAGMA foreign_keys=ON`，`database.get_db()` 已经开启。

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && .venv/bin/pytest tests -v
```

预期：22 passed。

- [ ] **Step 5: 提交**

```bash
git add backend/routers/fields.py backend/tests/test_fields_api.py
git commit -m "Add option CRUD, usage endpoints and cascade delete for fields"
```

---

### Task 6: 读取字段值并在日志详情中返回

**Files:**
- Create: `backend/field_values.py`
- Modify: `backend/routers/logs.py`
- Create: `backend/tests/test_log_field_values.py`

**Interfaces:**
- Consumes: Task 3 的 `FieldValueOut`；Task 4/5 的字段与选项端点
- Produces: `field_values.load_field_values(db, log_ids: Iterable[int], only_show_in_list: bool = False) -> dict[int, list[dict]]`；`field_values.SCALAR_COLUMN: dict[str, str]`；`logs.LOG_COLUMNS: str`

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_log_field_values.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && .venv/bin/pytest tests/test_log_field_values.py -v
```

预期：全部 FAIL（`field_values` 键不存在或为空）。

- [ ] **Step 3: 写 field_values.py 的读取逻辑**

`backend/field_values.py`：

```python
"""日志自定义字段值的读写与查询构造。

只依赖 sqlite3，不依赖 FastAPI —— 校验失败一律抛 ValueError，
由路由层翻译成 HTTP 400。
"""

SCALAR_COLUMN = {
    "text": "value_text",
    "textarea": "value_text",
    "number": "value_num",
    "date": "value_date",
}


def load_field_values(db, log_ids, only_show_in_list=False):
    """返回 {log_id: [字段值 dict, ...]}，每个 log 的字段按 sort_order 排列。

    一次查询取回所有 log 的值，调用方不要在循环里调它。
    """
    log_ids = list(log_ids)
    if not log_ids:
        return {}

    placeholders = ",".join("?" * len(log_ids))
    extra = " AND f.show_in_list = 1" if only_show_in_list else ""
    rows = db.execute(
        f"""
        SELECT v.log_id, v.field_id, f.name, f.type, f.sort_order, f.show_in_list,
               v.value_text, v.value_num, v.value_date, v.option_id,
               o.label AS option_label
        FROM log_field_values v
        JOIN category_fields f ON f.id = v.field_id
        LEFT JOIN field_options o ON o.id = v.option_id
        WHERE v.log_id IN ({placeholders}){extra}
        ORDER BY f.sort_order, f.id, o.sort_order, o.id
        """,
        log_ids,
    ).fetchall()

    grouped = {}
    for r in rows:
        bucket = grouped.setdefault(r["log_id"], {})
        entry = bucket.get(r["field_id"])
        if entry is None:
            entry = {
                "field_id": r["field_id"],
                "name": r["name"],
                "type": r["type"],
                "sort_order": r["sort_order"],
                "show_in_list": bool(r["show_in_list"]),
                "value": [] if r["type"] == "multiselect" else None,
                "option_labels": [],
            }
            bucket[r["field_id"]] = entry

        if r["type"] == "multiselect":
            entry["value"].append(r["option_id"])
            if r["option_label"] is not None:
                entry["option_labels"].append(r["option_label"])
        elif r["type"] == "select":
            entry["value"] = r["option_id"]
            entry["option_labels"] = (
                [r["option_label"]] if r["option_label"] is not None else []
            )
        else:
            entry["value"] = r[SCALAR_COLUMN[r["type"]]]

    return {log_id: list(bucket.values()) for log_id, bucket in grouped.items()}
```

- [ ] **Step 4: 让 logs.py 用上它**

`backend/routers/logs.py` 顶部 import 增加：

```python
from field_values import load_field_values
```

在 `UPLOAD_DIR` 定义之后新增列名常量（注意：所有列都带 `l.` 别名，且**不含 `wire`**）：

```python
LOG_COLUMNS = (
    "l.id, l.category_id, l.description, l.external_link, "
    "l.status, l.created_at, l.updated_at"
)
```

把 `_build_log` 改为：

```python
def _build_log(db: sqlite3.Connection, log_row) -> dict:
    log = dict(log_row)
    cat = db.execute(
        "SELECT name FROM categories WHERE id = ?", (log["category_id"],)
    ).fetchone()
    log["category_name"] = cat["name"] if cat else ""
    imgs = db.execute(
        "SELECT id, log_id, filename, original_name, created_at FROM images "
        "WHERE log_id = ? ORDER BY id",
        (log["id"],),
    ).fetchall()
    log["images"] = [dict(i) for i in imgs]
    log["field_values"] = load_field_values(db, [log["id"]]).get(log["id"], [])
    return log
```

把 `logs.py` 中**全部 5 处**日志行查询改成使用 `LOG_COLUMNS` 与 `logs l` 别名。逐处替换：

`list_logs` 中：

```python
    rows = db.execute(
        f"SELECT {LOG_COLUMNS} FROM logs l{where_clause} "
        f"ORDER BY l.created_at DESC LIMIT ? OFFSET ?",
        params + [size, offset],
    ).fetchall()
```

`create_log` 结尾、`get_log`、`update_log` 结尾、`toggle_status` 结尾这四处，统一改成：

```python
    row = db.execute(
        f"SELECT {LOG_COLUMNS} FROM logs l WHERE l.id = ?", (log_id,)
    ).fetchone()
```

`get_log` 那处保留软删过滤：

```python
    row = db.execute(
        f"SELECT {LOG_COLUMNS} FROM logs l WHERE l.id = ? AND l.deleted_at IS NULL",
        (log_id,),
    ).fetchone()
```

同时删除 `create_log` 的 `wire: str = Form("")` 形参、INSERT 语句里的 `wire` 列，以及 `update_log` 中处理 `body.wire` 的三行。`create_log` 的 INSERT 变为：

```python
    cur = db.execute(
        "INSERT INTO logs (category_id, description, external_link) VALUES (?, ?, ?)",
        (category_id, description, external_link),
    )
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && .venv/bin/pytest tests -v
```

预期：28 passed。

- [ ] **Step 6: 提交**

```bash
git add backend/field_values.py backend/routers/logs.py backend/tests/test_log_field_values.py
git commit -m "Return custom field values on log detail, drop wire from log queries"
```

---

### Task 7: 写入字段值与必填校验

**Files:**
- Modify: `backend/field_values.py`
- Modify: `backend/routers/logs.py`
- Modify: `backend/tests/test_log_field_values.py`

**Interfaces:**
- Consumes: Task 6 的 `load_field_values`、`LOG_COLUMNS`
- Produces: `field_values.save_field_values(db, log_id: int, category_id: int, values: dict) -> None`（校验失败抛 `ValueError`）

- [ ] **Step 1: 写失败的测试**

追加到 `backend/tests/test_log_field_values.py`：

```python
import json


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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && .venv/bin/pytest tests/test_log_field_values.py -v
```

预期：8 个新测试 FAIL。

- [ ] **Step 3: 实现 save_field_values**

追加到 `backend/field_values.py`：

```python
def _is_empty(value):
    return value is None or value == "" or value == []


def save_field_values(db, log_id, category_id, values):
    """全量替换某条日志的自定义字段值。

    values 的 key 是 field_id（字符串或整数皆可），value 的形状取决于字段类型：
    标量类型是标量，select 是 option_id，multiselect 是 option_id 列表。
    校验失败抛 ValueError，由路由层翻译成 400。
    """
    fields = {
        r["id"]: r
        for r in db.execute(
            "SELECT id, name, type, required FROM category_fields WHERE category_id = ?",
            (category_id,),
        ).fetchall()
    }

    normalized = {}
    for raw_key, raw_value in values.items():
        try:
            field_id = int(raw_key)
        except (TypeError, ValueError):
            raise ValueError(f"非法的字段 id: {raw_key}")
        if field_id not in fields:
            raise ValueError(f"字段 {field_id} 不属于该分类")
        normalized[field_id] = raw_value

    for field_id, field in fields.items():
        if field["required"] and _is_empty(normalized.get(field_id)):
            raise ValueError(f"字段「{field['name']}」为必填")

    for field_id, value in normalized.items():
        db.execute(
            "DELETE FROM log_field_values WHERE log_id = ? AND field_id = ?",
            (log_id, field_id),
        )
        if _is_empty(value):
            continue

        field = fields[field_id]
        ftype = field["type"]
        if ftype == "multiselect":
            seen = set()
            for raw_option in value:
                option_id = int(raw_option)
                if option_id in seen:
                    continue
                seen.add(option_id)
                db.execute(
                    "INSERT INTO log_field_values (log_id, field_id, option_id) "
                    "VALUES (?, ?, ?)",
                    (log_id, field_id, option_id),
                )
        elif ftype == "select":
            db.execute(
                "INSERT INTO log_field_values (log_id, field_id, option_id) "
                "VALUES (?, ?, ?)",
                (log_id, field_id, int(value)),
            )
        elif ftype == "number":
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"字段「{field['name']}」需要填数字")
            db.execute(
                "INSERT INTO log_field_values (log_id, field_id, value_num) "
                "VALUES (?, ?, ?)",
                (log_id, field_id, number),
            )
        elif ftype == "date":
            db.execute(
                "INSERT INTO log_field_values (log_id, field_id, value_date) "
                "VALUES (?, ?, ?)",
                (log_id, field_id, str(value)),
            )
        else:
            db.execute(
                "INSERT INTO log_field_values (log_id, field_id, value_text) "
                "VALUES (?, ?, ?)",
                (log_id, field_id, str(value)),
            )
```

- [ ] **Step 4: 在 logs.py 中接上**

import 改为：

```python
import json
from field_values import load_field_values, save_field_values
```

在 `_build_log` 之后加一个翻译辅助：

```python
def _apply_field_values(db, log_id: int, category_id: int, values: dict):
    try:
        save_field_values(db, log_id, category_id, values)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
```

`create_log` 增加 form 形参并在插入日志后、写图片之前调用。签名加一行：

```python
    field_values: str = Form("{}"),
```

在 `log_id = cur.lastrowid` 与 `db.commit()` 之后插入：

```python
    try:
        parsed_values = json.loads(field_values or "{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "field_values 不是合法的 JSON")
    if not isinstance(parsed_values, dict):
        raise HTTPException(400, "field_values 必须是对象")
    _apply_field_values(db, log_id, category_id, parsed_values)
    db.commit()
```

`update_log` 在现有 `if updates:` 块之后、重新查询 row 之前插入：

```python
    if body.field_values is not None:
        target_category = body.category_id
        if target_category is None:
            target_category = db.execute(
                "SELECT category_id FROM logs WHERE id = ?", (log_id,)
            ).fetchone()["category_id"]
        _apply_field_values(db, log_id, target_category, body.field_values)
        db.commit()
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && .venv/bin/pytest tests -v
```

预期：36 passed。

- [ ] **Step 6: 提交**

```bash
git add backend/field_values.py backend/routers/logs.py backend/tests/test_log_field_values.py
git commit -m "Accept custom field values on log create and update"
```

---

### Task 8: 列表筛选与排序

**Files:**
- Modify: `backend/field_values.py`
- Modify: `backend/routers/logs.py`
- Create: `backend/tests/test_log_filter_sort.py`

**Interfaces:**
- Consumes: Task 6/7 的 `load_field_values`、`save_field_values`、`LOG_COLUMNS`
- Produces: `field_values.build_option_filters(fv_params: list[str]) -> tuple[list[str], list]`；`field_values.build_sort(db, sort_param: str | None) -> tuple[str, list, str]`

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_log_filter_sort.py`：

```python
import json
import pytest


@pytest.fixture()
def setup(client):
    """建一个分类，含 品牌(select)、类型(multiselect)、价格(number)、日期(date) 四个字段。"""
    category = client.post("/api/categories", json={"name": "欢欢衣服"}).json()
    cid = category["id"]

    brand = client.post(
        f"/api/categories/{cid}/fields", json={"name": "品牌", "type": "select", "sort_order": 1}
    ).json()
    kind = client.post(
        f"/api/categories/{cid}/fields",
        json={"name": "衣服类型", "type": "multiselect", "sort_order": 2},
    ).json()
    price = client.post(
        f"/api/categories/{cid}/fields", json={"name": "购入价格", "type": "number", "sort_order": 3}
    ).json()
    bought = client.post(
        f"/api/categories/{cid}/fields", json={"name": "购入日期", "type": "date", "sort_order": 4}
    ).json()

    def opts(field, labels):
        return [
            client.post(f"/api/fields/{field['id']}/options", json={"label": label}).json()
            for label in labels
        ]

    brands = opts(brand, ["Nike", "Adidas", "Uniqlo"])
    kinds = opts(kind, ["外套", "卫衣"])

    def make(description, values):
        return client.post(
            "/api/logs",
            data={
                "category_id": cid,
                "description": description,
                "field_values": json.dumps(values),
            },
        ).json()

    logs = {
        "nike_coat": make("Nike外套", {
            str(brand["id"]): brands[0]["id"],
            str(kind["id"]): [kinds[0]["id"]],
            str(price["id"]): 899,
            str(bought["id"]): "2026-03-01",
        }),
        "adidas_hoodie": make("Adidas卫衣", {
            str(brand["id"]): brands[1]["id"],
            str(kind["id"]): [kinds[1]["id"]],
            str(price["id"]): 499,
            str(bought["id"]): "2026-01-15",
        }),
        "uniqlo_both": make("Uniqlo两种", {
            str(brand["id"]): brands[2]["id"],
            str(kind["id"]): [kinds[0]["id"], kinds[1]["id"]],
        }),
    }
    return {
        "category": category, "brand": brand, "kind": kind,
        "price": price, "bought": bought,
        "brands": brands, "kinds": kinds, "logs": logs,
    }


def _descriptions(body):
    return [item["description"] for item in body["items"]]


def test_filter_by_single_option(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "fv": [f"{setup['brand']['id']}:{setup['brands'][0]['id']}"]},
    ).json()
    assert _descriptions(body) == ["Nike外套"]
    assert body["total"] == 1


def test_same_field_multiple_options_is_or(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"], "fv": [
            f"{setup['brand']['id']}:{setup['brands'][0]['id']}",
            f"{setup['brand']['id']}:{setup['brands'][1]['id']}",
        ]},
    ).json()
    assert set(_descriptions(body)) == {"Nike外套", "Adidas卫衣"}


def test_different_fields_are_and(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"], "fv": [
            f"{setup['brand']['id']}:{setup['brands'][0]['id']}",
            f"{setup['kind']['id']}:{setup['kinds'][1]['id']}",
        ]},
    ).json()
    assert _descriptions(body) == []


def test_multiselect_filter_matches_any_selected_option(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "fv": [f"{setup['kind']['id']}:{setup['kinds'][0]['id']}"]},
    ).json()
    assert set(_descriptions(body)) == {"Nike外套", "Uniqlo两种"}


def test_sort_by_number_desc_puts_empty_last(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "sort": f"{setup['price']['id']}:desc"},
    ).json()
    assert _descriptions(body) == ["Nike外套", "Adidas卫衣", "Uniqlo两种"]


def test_sort_by_number_asc_puts_empty_last(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "sort": f"{setup['price']['id']}:asc"},
    ).json()
    assert _descriptions(body) == ["Adidas卫衣", "Nike外套", "Uniqlo两种"]


def test_sort_by_date_asc(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "sort": f"{setup['bought']['id']}:asc"},
    ).json()
    assert _descriptions(body)[:2] == ["Adidas卫衣", "Nike外套"]


def test_sort_by_non_sortable_field_falls_back(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "sort": f"{setup['brand']['id']}:asc"},
    ).json()
    assert _descriptions(body) == ["Uniqlo两种", "Adidas卫衣", "Nike外套"]


def test_garbage_filter_and_sort_params_are_ignored(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "fv": ["abc", "1:", ":2"], "sort": "垃圾"},
    ).json()
    assert body["total"] == 3


def test_filter_total_reflects_filtered_count(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "fv": [f"{setup['kind']['id']}:{setup['kinds'][0]['id']}"]},
    ).json()
    assert body["total"] == 2
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && .venv/bin/pytest tests/test_log_filter_sort.py -v
```

预期：筛选与排序相关测试 FAIL（参数被忽略，返回全部 3 条）。

- [ ] **Step 3: 实现查询构造器**

追加到 `backend/field_values.py`：

```python
SORTABLE_COLUMN = {"number": "s.value_num", "date": "s.value_date"}


def build_option_filters(fv_params):
    """把 ['12:34', '12:35', '13:56'] 转成 (WHERE 子句列表, 参数列表)。

    同一字段内的多个选项是 OR，不同字段之间是 AND。
    对 multiselect 而言这正好等价于「包含任一选中项」。
    非法格式的条目直接忽略。
    """
    grouped = {}
    for item in fv_params or []:
        if ":" not in item:
            continue
        raw_field, raw_option = item.split(":", 1)
        if not raw_field.isdigit() or not raw_option.isdigit():
            continue
        grouped.setdefault(int(raw_field), []).append(int(raw_option))

    clauses, params = [], []
    for field_id, option_ids in grouped.items():
        placeholders = ",".join("?" * len(option_ids))
        clauses.append(
            "EXISTS (SELECT 1 FROM log_field_values v "
            f"WHERE v.log_id = l.id AND v.field_id = ? "
            f"AND v.option_id IN ({placeholders}))"
        )
        params.append(field_id)
        params.extend(option_ids)
    return clauses, params


def build_sort(db, sort_param):
    """把 '15:desc' 转成 (JOIN 子句, JOIN 参数, ORDER BY 子句)。

    只有 number 与 date 类型的字段可排序；其余一律回落到 created_at DESC。
    """
    default = ("", [], "l.created_at DESC")
    if not sort_param or ":" not in sort_param:
        return default

    raw_field, direction = sort_param.split(":", 1)
    if not raw_field.isdigit() or direction not in ("asc", "desc"):
        return default

    row = db.execute(
        "SELECT type FROM category_fields WHERE id = ?", (int(raw_field),)
    ).fetchone()
    if not row or row["type"] not in SORTABLE_COLUMN:
        return default

    column = SORTABLE_COLUMN[row["type"]]
    join_sql = " LEFT JOIN log_field_values s ON s.log_id = l.id AND s.field_id = ?"
    order_sql = f"{column} {direction.upper()} NULLS LAST, l.created_at DESC"
    return join_sql, [int(raw_field)], order_sql
```

- [ ] **Step 4: 改写 list_logs**

`backend/routers/logs.py` 顶部 import 补 `Query` 与两个构造器：

```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from field_values import (
    load_field_values,
    save_field_values,
    build_option_filters,
    build_sort,
)
```

把整个 `list_logs` 换成：

```python
@router.get("", response_model=LogListOut)
def list_logs(
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    status: Optional[str] = None,
    fv: list[str] = Query(default=[]),
    sort: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    db: sqlite3.Connection = Depends(get_db),
):
    where, params = ["l.deleted_at IS NULL"], []
    if search:
        where.append("l.description LIKE ?")
        params.append(f"%{search}%")
    if category_id is not None:
        where.append("l.category_id = ?")
        params.append(category_id)
    if status:
        where.append("l.status = ?")
        params.append(status)

    fv_clauses, fv_params = build_option_filters(fv)
    where.extend(fv_clauses)
    params.extend(fv_params)

    where_clause = " WHERE " + " AND ".join(where)

    total = db.execute(
        f"SELECT COUNT(*) AS c FROM logs l{where_clause}", params
    ).fetchone()["c"]

    join_sql, join_params, order_sql = build_sort(db, sort)
    offset = (page - 1) * size
    rows = db.execute(
        f"SELECT {LOG_COLUMNS} FROM logs l{join_sql}{where_clause} "
        f"ORDER BY {order_sql} LIMIT ? OFFSET ?",
        join_params + params + [size, offset],
    ).fetchall()

    items = [_build_log(db, r) for r in rows]
    return {"items": items, "total": total, "page": page, "size": size}
```

> 参数顺序很关键：JOIN 的占位符在 SQL 文本中出现在 WHERE 之前，
> 所以必须是 `join_params + params + [size, offset]`。
> COUNT 查询不带 JOIN，因此只传 `params`。

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && .venv/bin/pytest tests -v
```

预期：46 passed。

- [ ] **Step 6: 提交**

```bash
git add backend/field_values.py backend/routers/logs.py backend/tests/test_log_filter_sort.py
git commit -m "Add custom field filtering and sorting to the log list"
```

---

### Task 9: 列表批量加载与 show_in_list

**Files:**
- Modify: `backend/routers/logs.py`
- Modify: `backend/tests/test_log_filter_sort.py`

**Interfaces:**
- Consumes: Task 6 的 `load_field_values`（`only_show_in_list` 参数）
- Produces: `logs._build_log_list(db, rows) -> list[dict]`

- [ ] **Step 1: 写失败的测试**

追加到 `backend/tests/test_log_filter_sort.py`：

```python
def test_list_only_returns_show_in_list_fields(client, setup):
    client.put(f"/api/fields/{setup['brand']['id']}", json={"show_in_list": True})

    body = client.get(
        "/api/logs", params={"category_id": setup["category"]["id"]}
    ).json()
    nike = next(i for i in body["items"] if i["description"] == "Nike外套")
    assert [fv["name"] for fv in nike["field_values"]] == ["品牌"]
    assert nike["field_values"][0]["option_labels"] == ["Nike"]


def test_detail_still_returns_all_fields(client, setup):
    client.put(f"/api/fields/{setup['brand']['id']}", json={"show_in_list": True})
    log_id = setup["logs"]["nike_coat"]["id"]

    body = client.get(f"/api/logs/{log_id}").json()
    assert [fv["name"] for fv in body["field_values"]] == [
        "品牌", "衣服类型", "购入价格", "购入日期"
    ]


def test_list_with_no_show_in_list_fields_returns_empty(client, setup):
    body = client.get(
        "/api/logs", params={"category_id": setup["category"]["id"]}
    ).json()
    assert all(item["field_values"] == [] for item in body["items"])


def test_list_issues_constant_number_of_queries(client, setup):
    """回归护栏：列表端点不得随日志条数增加查询次数。

    注意：不能用 monkeypatch 去打 sqlite3.Connection.execute —— 它是不可变的
    C 扩展类型，赋值会抛 TypeError。改用依赖覆盖注入一个开了 trace 的连接。
    """
    import sqlite3
    import database
    from main import app

    statements = []

    def tracing_db():
        conn = sqlite3.connect(database.DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.set_trace_callback(statements.append)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[database.get_db] = tracing_db
    try:
        client.get("/api/logs", params={"category_id": setup["category"]["id"]})
    finally:
        app.dependency_overrides.pop(database.get_db, None)

    image_queries = [s for s in statements if "FROM images" in s]
    assert len(image_queries) <= 1, f"图片查询发生了 {len(image_queries)} 次，应当只有 1 次"


def test_list_preserves_category_name(client, setup):
    body = client.get(
        "/api/logs", params={"category_id": setup["category"]["id"]}
    ).json()
    assert all(item["category_name"] == "欢欢衣服" for item in body["items"])
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && .venv/bin/pytest tests/test_log_filter_sort.py -v
```

预期：`test_list_only_returns_show_in_list_fields`（列表返回了全部字段）与
`test_list_issues_constant_number_of_queries`（图片查询 3 次）FAIL。

- [ ] **Step 3: 实现批量组装**

在 `backend/routers/logs.py` 的 `_build_log` 之后追加：

```python
def _build_log_list(db: sqlite3.Connection, rows) -> list[dict]:
    """批量组装列表项：图片与字段值各一次查询，避免随条数增长的 N+1。"""
    logs = [dict(r) for r in rows]
    if not logs:
        return []

    log_ids = [log["id"] for log in logs]
    placeholders = ",".join("?" * len(log_ids))

    category_names = {
        r["id"]: r["name"]
        for r in db.execute("SELECT id, name FROM categories").fetchall()
    }

    images: dict[int, list[dict]] = {}
    for r in db.execute(
        "SELECT id, log_id, filename, original_name, created_at FROM images "
        f"WHERE log_id IN ({placeholders}) ORDER BY id",
        log_ids,
    ).fetchall():
        images.setdefault(r["log_id"], []).append(dict(r))

    values = load_field_values(db, log_ids, only_show_in_list=True)

    for log in logs:
        log["category_name"] = category_names.get(log["category_id"], "")
        log["images"] = images.get(log["id"], [])
        log["field_values"] = values.get(log["id"], [])
    return logs
```

把 `list_logs` 末尾的

```python
    items = [_build_log(db, r) for r in rows]
```

改成

```python
    items = _build_log_list(db, rows)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && .venv/bin/pytest tests -v
```

预期：51 passed。后端全部完成。

- [ ] **Step 5: 提交**

```bash
git add backend/routers/logs.py backend/tests/test_log_filter_sort.py
git commit -m "Batch-load list payload and limit list fields to show_in_list"
```

---

## 前端任务说明

前端不引入测试框架（见 Global Constraints），因此 Task 10-16 的验证方式是
**`npm run build` 必须通过 + 明确列出的手工验证步骤**。

本地起全栈环境：

```bash
# 终端 1 — 后端（务必覆盖 DB_PATH / UPLOAD_DIR，否则会写到容器路径）
cd backend && DB_PATH=./devdata/piclog.db UPLOAD_DIR=./devuploads \
  .venv/bin/python -m uvicorn main:app --reload --port 8080

# 终端 2 — 前端，访问 http://localhost:5173
cd frontend && npm run dev
```

首次手工验证前，在「分类管理」里建一个分类「欢欢衣服」，后面的步骤都基于它。

---

### Task 10: API 客户端封装

**Files:**
- Modify: `frontend/src/api.js`

**Interfaces:**
- Consumes: Task 4/5 的字段与选项端点
- Produces: `api.getCategoryFields(cid)`、`api.createField(cid, data)`、`api.updateField(fid, data)`、`api.deleteField(fid)`、`api.getFieldUsage(fid)`、`api.createOption(fid, data)`、`api.updateOption(oid, data)`、`api.deleteOption(oid)`、`api.getOptionUsage(oid)`；`api.getLogs` 支持数组值参数

- [ ] **Step 1: 让 getLogs 支持数组参数**

把 `frontend/src/api.js` 中的 `getLogs` 换成：

```js
  getLogs: (params = {}) => {
    const q = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v === null || v === undefined || v === '') continue
      if (Array.isArray(v)) {
        for (const item of v) q.append(k, item)
      } else {
        q.set(k, v)
      }
    }
    return request(`/api/logs?${q}`)
  },
```

- [ ] **Step 2: 新增字段与选项端点**

在 `deleteCategory` 那一行之后、`// Logs` 注释之前插入：

```js
  // Category fields
  getCategoryFields: (cid) => request(`/api/categories/${cid}/fields`),
  createField: (cid, data) => request(`/api/categories/${cid}/fields`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }),
  updateField: (fid, data) => request(`/api/fields/${fid}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }),
  deleteField: (fid) => request(`/api/fields/${fid}`, { method: 'DELETE' }),
  getFieldUsage: (fid) => request(`/api/fields/${fid}/usage`),

  // Field options
  createOption: (fid, data) => request(`/api/fields/${fid}/options`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }),
  updateOption: (oid, data) => request(`/api/options/${oid}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }),
  deleteOption: (oid) => request(`/api/options/${oid}`, { method: 'DELETE' }),
  getOptionUsage: (oid) => request(`/api/options/${oid}/usage`),
```

- [ ] **Step 3: 构建验证**

```bash
cd frontend && npm run build
```

预期：build 成功，无报错。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/api.js
git commit -m "Add API client methods for category fields and options"
```

---

### Task 11: 字段管理页（字段 CRUD）

**Files:**
- Create: `frontend/src/views/CategoryFields.vue`
- Modify: `frontend/src/router.js`
- Modify: `frontend/src/views/Categories.vue`

**Interfaces:**
- Consumes: Task 10 的 `api.getCategoryFields` / `createField` / `updateField` / `deleteField` / `getFieldUsage`
- Produces: 路由 `/categories/:id/fields`（name `CategoryFields`）

- [ ] **Step 1: 创建字段管理页**

`frontend/src/views/CategoryFields.vue`：

```vue
<template>
  <div>
    <PageHeader :title="categoryName ? `${categoryName} · 字段` : '字段管理'" back />

    <!-- Add field -->
    <form
      @submit.prevent="addField"
      class="mb-4 space-y-2 rounded-2xl border border-slate-100 bg-white p-3 shadow-sm"
    >
      <div class="flex items-center gap-2">
        <input
          type="text"
          v-model="newField.name"
          placeholder="字段名称"
          required
          class="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 transition-colors focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        />
        <select
          v-model="newField.type"
          class="shrink-0 rounded-xl border border-slate-200 bg-white px-2.5 py-2 text-sm text-slate-900 shadow-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        >
          <option v-for="t in FIELD_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
        <input
          type="text"
          v-model.number="newField.sort_order"
          placeholder="排序"
          class="w-14 shrink-0 rounded-xl border border-slate-200 bg-white px-2 py-2 text-center text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        />
      </div>
      <div class="flex items-center gap-4">
        <label class="flex items-center gap-1.5 text-xs text-slate-600">
          <input type="checkbox" v-model="newField.required" class="h-3.5 w-3.5 rounded border-slate-300 text-primary-600 focus:ring-primary-400" />
          必填
        </label>
        <label class="flex items-center gap-1.5 text-xs text-slate-600">
          <input type="checkbox" v-model="newField.show_in_list" class="h-3.5 w-3.5 rounded border-slate-300 text-primary-600 focus:ring-primary-400" />
          显示在列表卡片
        </label>
        <button
          type="submit"
          class="ml-auto shrink-0 rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-primary-700"
        >
          添加字段
        </button>
      </div>
    </form>

    <!-- Too many cards hint -->
    <p
      v-if="shownInListCount > 3"
      class="mb-3 rounded-xl bg-amber-50 px-3.5 py-2 text-xs text-amber-700"
    >
      已有 {{ shownInListCount }} 个字段标记为显示在列表卡片。卡片空间有限，建议不超过 3 个。
    </p>

    <EmptyState v-if="fields.length === 0" message="该分类还没有字段" />

    <!-- Field list -->
    <div v-else class="overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-sm divide-y divide-slate-100">
      <div v-for="f in fields" :key="f.id" class="px-4 py-3">
        <!-- Edit mode -->
        <form v-if="editing === f.id" @submit.prevent="saveEdit(f)" class="space-y-2">
          <div class="flex items-center gap-2">
            <input
              type="text"
              v-model="editForm.name"
              required
              class="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-900 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
            />
            <span
              class="shrink-0 rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs text-slate-400"
              title="字段类型创建后不可修改，需要改请删除后重建"
            >
              {{ typeLabel(f.type) }}
            </span>
            <input
              type="text"
              v-model.number="editForm.sort_order"
              class="w-12 shrink-0 rounded-lg border border-slate-200 px-2 py-1.5 text-center text-sm text-slate-900 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
            />
          </div>
          <div class="flex items-center gap-4">
            <label class="flex items-center gap-1.5 text-xs text-slate-600">
              <input type="checkbox" v-model="editForm.required" class="h-3.5 w-3.5 rounded border-slate-300 text-primary-600 focus:ring-primary-400" />
              必填
            </label>
            <label class="flex items-center gap-1.5 text-xs text-slate-600">
              <input type="checkbox" v-model="editForm.show_in_list" class="h-3.5 w-3.5 rounded border-slate-300 text-primary-600 focus:ring-primary-400" />
              显示在列表卡片
            </label>
            <button type="submit" class="ml-auto shrink-0 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-700">
              保存
            </button>
            <button type="button" @click="editing = null" class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100">
              取消
            </button>
          </div>
        </form>

        <!-- Display mode -->
        <div v-else>
          <div class="flex items-center justify-between">
            <div class="flex min-w-0 items-center gap-2">
              <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-xs font-bold text-primary-600">
                {{ f.sort_order }}
              </span>
              <span class="truncate text-sm font-medium text-slate-900">{{ f.name }}</span>
              <span class="shrink-0 rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                {{ typeLabel(f.type) }}
              </span>
              <span v-if="f.required" class="shrink-0 rounded-md bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-500">
                必填
              </span>
              <span v-if="f.show_in_list" class="shrink-0 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600">
                列表
              </span>
            </div>
            <div class="flex shrink-0 items-center gap-1">
              <button
                @click="startEdit(f)"
                class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
              >
                <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" />
                </svg>
              </button>
              <button
                @click="removeField(f)"
                class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-red-50 hover:text-red-500"
              >
                <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api.js'
import PageHeader from '../components/PageHeader.vue'
import EmptyState from '../components/EmptyState.vue'

const FIELD_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'textarea', label: '多行文本' },
  { value: 'number', label: '数字' },
  { value: 'date', label: '日期' },
  { value: 'select', label: '下拉' },
  { value: 'multiselect', label: '多选' },
]

const route = useRoute()
const categoryId = Number(route.params.id)

const categoryName = ref('')
const fields = ref([])
const editing = ref(null)
const editForm = ref({ name: '', sort_order: 0, required: false, show_in_list: false })
const newField = ref({ name: '', type: 'text', sort_order: 0, required: false, show_in_list: false })

const shownInListCount = computed(() => fields.value.filter((f) => f.show_in_list).length)

function typeLabel(value) {
  const hit = FIELD_TYPES.find((t) => t.value === value)
  return hit ? hit.label : value
}

async function load() {
  fields.value = await api.getCategoryFields(categoryId)
}

async function loadCategoryName() {
  const all = await api.getCategories()
  const hit = all.find((c) => c.id === categoryId)
  categoryName.value = hit ? hit.name : ''
}

async function addField() {
  if (!newField.value.name.trim()) return
  try {
    await api.createField(categoryId, {
      name: newField.value.name.trim(),
      type: newField.value.type,
      sort_order: newField.value.sort_order || 0,
      required: newField.value.required,
      show_in_list: newField.value.show_in_list,
    })
    newField.value = { name: '', type: 'text', sort_order: 0, required: false, show_in_list: false }
    await load()
  } catch (e) {
    alert(e.message)
  }
}

function startEdit(f) {
  editing.value = f.id
  editForm.value = {
    name: f.name,
    sort_order: f.sort_order,
    required: f.required,
    show_in_list: f.show_in_list,
  }
}

async function saveEdit(f) {
  try {
    await api.updateField(f.id, {
      name: editForm.value.name.trim(),
      sort_order: editForm.value.sort_order,
      required: editForm.value.required,
      show_in_list: editForm.value.show_in_list,
    })
    editing.value = null
    await load()
  } catch (e) {
    alert(e.message)
  }
}

async function removeField(f) {
  try {
    const { log_count } = await api.getFieldUsage(f.id)
    const message = log_count > 0
      ? `字段「${f.name}」已被 ${log_count} 条日志使用，删除会一并清除这些数据。确定删除？`
      : `确定删除字段「${f.name}」？`
    if (!confirm(message)) return
    await api.deleteField(f.id)
    await load()
  } catch (e) {
    alert(e.message)
  }
}

onMounted(async () => {
  await loadCategoryName()
  await load()
})
</script>
```

- [ ] **Step 2: 注册路由**

`frontend/src/router.js` 增加 import 与路由项：

```js
import CategoryFields from './views/CategoryFields.vue'
```

```js
  { path: '/categories', name: 'Categories', component: Categories },
  { path: '/categories/:id/fields', name: 'CategoryFields', component: CategoryFields },
```

- [ ] **Step 3: 在分类管理页加入口**

`frontend/src/views/Categories.vue` 的 display mode 区块中，把分类名那个 `<span>` 换成可点击的链接，并在按钮组最前面加一个「字段」入口。把这段：

```html
            <span class="text-sm font-medium text-slate-900">{{ c.name }}</span>
```

换成：

```html
            <router-link
              :to="`/categories/${c.id}/fields`"
              class="text-sm font-medium text-slate-900 hover:text-primary-600"
            >
              {{ c.name }}
            </router-link>
```

并在 `<div class="flex items-center gap-1">` 内、编辑按钮之前插入：

```html
            <router-link
              :to="`/categories/${c.id}/fields`"
              class="flex h-8 items-center rounded-lg px-2 text-xs font-medium text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            >
              字段
            </router-link>
```

- [ ] **Step 4: 构建验证**

```bash
cd frontend && npm run build
```

预期：build 成功。

- [ ] **Step 5: 手工验证**

启动全栈环境后：

1. 进入「分类管理」，点击「欢欢衣服」或它右侧的「字段」→ 进入字段管理页，标题显示「欢欢衣服 · 字段」
2. 添加字段「购入价格」，类型选「数字」，勾选「显示在列表卡片」，排序填 3 → 列表出现该字段，带「列表」徽章
3. 添加「购入日期」（日期）、「品牌」（下拉）、「衣服类型」（多选）、「购买地」（下拉）
4. 点编辑「购入价格」→ 类型显示为灰色不可改的「数字」，改名后保存生效
5. 再把两个字段也勾上「显示在列表卡片」，使总数达到 4 → 页面顶部出现琥珀色提示
6. 删除一个没被使用的字段 → 确认框文案是「确定删除字段「X」？」，删除成功

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/CategoryFields.vue frontend/src/router.js frontend/src/views/Categories.vue
git commit -m "Add category field management page"
```

---

### Task 12: 选项管理 UI

**Files:**
- Modify: `frontend/src/views/CategoryFields.vue`

**Interfaces:**
- Consumes: Task 10 的 `api.createOption` / `updateOption` / `deleteOption` / `getOptionUsage`
- Produces: 无（页面内交互）

- [ ] **Step 1: 在字段行下方加入选项区块**

在 `CategoryFields.vue` 的 display mode 区块内，紧跟 `</div>`（即 `flex items-center justify-between` 那一层的闭合）之后、`</div>`（display mode 的外层）之前，插入：

```html
          <!-- Options for select / multiselect -->
          <div v-if="hasOptions(f)" class="mt-2 pl-9">
            <button
              @click="toggleOptions(f.id)"
              class="text-xs font-medium text-primary-600 hover:text-primary-700"
            >
              {{ expanded === f.id ? '收起选项' : `选项（${f.options.length}）` }}
            </button>

            <div v-if="expanded === f.id" class="mt-2 space-y-1.5">
              <div
                v-for="o in f.options"
                :key="o.id"
                class="flex items-center gap-2 rounded-lg bg-slate-50 px-2.5 py-1.5"
              >
                <template v-if="editingOption === o.id">
                  <input
                    type="text"
                    v-model="optionForm.label"
                    class="min-w-0 flex-1 rounded border border-slate-200 bg-white px-2 py-1 text-xs text-slate-900 focus:border-primary-400 focus:outline-none"
                  />
                  <input
                    type="text"
                    v-model.number="optionForm.sort_order"
                    class="w-10 shrink-0 rounded border border-slate-200 bg-white px-1 py-1 text-center text-xs text-slate-900 focus:border-primary-400 focus:outline-none"
                  />
                  <button @click="saveOption(o)" class="shrink-0 rounded bg-primary-600 px-2 py-1 text-[10px] font-medium text-white hover:bg-primary-700">
                    保存
                  </button>
                  <button @click="editingOption = null" class="shrink-0 px-1 text-[10px] text-slate-500 hover:text-slate-700">
                    取消
                  </button>
                </template>
                <template v-else>
                  <span class="w-6 shrink-0 text-[10px] text-slate-400">{{ o.sort_order }}</span>
                  <span class="min-w-0 flex-1 truncate text-xs text-slate-700">{{ o.label }}</span>
                  <button @click="startEditOption(o)" class="shrink-0 px-1 text-[10px] text-slate-400 hover:text-slate-600">
                    改名
                  </button>
                  <button @click="removeOption(o)" class="shrink-0 px-1 text-[10px] text-slate-400 hover:text-red-500">
                    删除
                  </button>
                </template>
              </div>

              <form @submit.prevent="addOption(f)" class="flex items-center gap-2 pt-0.5">
                <input
                  type="text"
                  v-model="newOption.label"
                  placeholder="新选项名称"
                  required
                  class="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-900 placeholder:text-slate-400 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
                />
                <input
                  type="text"
                  v-model.number="newOption.sort_order"
                  placeholder="序"
                  class="w-10 shrink-0 rounded-lg border border-slate-200 bg-white px-1 py-1.5 text-center text-xs text-slate-900 placeholder:text-slate-400 focus:border-primary-400 focus:outline-none"
                />
                <button type="submit" class="shrink-0 rounded-lg bg-slate-900 px-2.5 py-1.5 text-[10px] font-medium text-white hover:bg-slate-700">
                  添加
                </button>
              </form>
            </div>
          </div>
```

- [ ] **Step 2: 补脚本逻辑**

在 `CategoryFields.vue` 的 `<script setup>` 中，`editForm` 声明之后追加状态：

```js
const expanded = ref(null)
const editingOption = ref(null)
const optionForm = ref({ label: '', sort_order: 0 })
const newOption = ref({ label: '', sort_order: 0 })
```

在 `typeLabel` 之后追加方法：

```js
function hasOptions(field) {
  return field.type === 'select' || field.type === 'multiselect'
}

function toggleOptions(fieldId) {
  expanded.value = expanded.value === fieldId ? null : fieldId
  editingOption.value = null
  newOption.value = { label: '', sort_order: 0 }
}

async function addOption(field) {
  if (!newOption.value.label.trim()) return
  try {
    await api.createOption(field.id, {
      label: newOption.value.label.trim(),
      sort_order: newOption.value.sort_order || 0,
    })
    newOption.value = { label: '', sort_order: 0 }
    await load()
  } catch (e) {
    alert(e.message)
  }
}

function startEditOption(option) {
  editingOption.value = option.id
  optionForm.value = { label: option.label, sort_order: option.sort_order }
}

async function saveOption(option) {
  try {
    await api.updateOption(option.id, {
      label: optionForm.value.label.trim(),
      sort_order: optionForm.value.sort_order,
    })
    editingOption.value = null
    await load()
  } catch (e) {
    alert(e.message)
  }
}

async function removeOption(option) {
  try {
    const { log_count } = await api.getOptionUsage(option.id)
    const message = log_count > 0
      ? `选项「${option.label}」已被 ${log_count} 条日志使用，删除会一并清除这些数据。确定删除？`
      : `确定删除选项「${option.label}」？`
    if (!confirm(message)) return
    await api.deleteOption(option.id)
    await load()
  } catch (e) {
    alert(e.message)
  }
}
```

> `load()` 会重新拉取整个字段列表（选项内嵌其中），所以每次增删改选项后
> 直接 `await load()` 即可刷新，不需要单独维护选项状态。

- [ ] **Step 3: 构建验证**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: 手工验证**

1. 在字段管理页找到「品牌」（下拉）字段 → 下方出现「选项（0）」按钮，点开
2. 添加选项 Nike、Adidas、Uniqlo → 按钮文案变成「选项（3）」
3. 给「衣服类型」（多选）添加「外套」「卫衣」
4. 把 Nike 改名成 NIKE → 列表立即显示新名字
5. 「购入价格」（数字）字段下方**不应**出现选项按钮
6. 删除一个未被使用的选项 → 确认文案为「确定删除选项「X」？」

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/CategoryFields.vue
git commit -m "Add option management to the field editor"
```

---

### Task 13: 日志表单的动态字段

**Files:**
- Create: `frontend/src/components/DynamicField.vue`
- Modify: `frontend/src/views/LogForm.vue`

**Interfaces:**
- Consumes: Task 10 的 `api.getCategoryFields`；Task 7 的 `field_values` 写入契约
- Produces: `DynamicField` 组件，props `field`（字段定义对象）与 `modelValue`，emit `update:modelValue`

- [ ] **Step 1: 创建 DynamicField 组件**

`frontend/src/components/DynamicField.vue`：

```vue
<template>
  <div>
    <label class="mb-1.5 block text-sm font-medium text-slate-700">
      {{ field.name }}
      <span v-if="field.required" class="text-red-500">*</span>
    </label>

    <!-- textarea -->
    <textarea
      v-if="field.type === 'textarea'"
      :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value)"
      rows="3"
      :placeholder="`${field.name}（可选）`"
      :class="inputClass"
    ></textarea>

    <!-- select -->
    <select
      v-else-if="field.type === 'select'"
      :value="modelValue === '' || modelValue === null ? '' : String(modelValue)"
      @change="onSelect($event)"
      :class="`${inputClass} appearance-none`"
    >
      <option value="">请选择</option>
      <option v-for="o in field.options" :key="o.id" :value="String(o.id)">{{ o.label }}</option>
    </select>

    <!-- multiselect -->
    <div v-else-if="field.type === 'multiselect'" class="flex flex-wrap gap-2">
      <label
        v-for="o in field.options"
        :key="o.id"
        class="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border px-3 py-1.5 text-sm transition-colors"
        :class="isChecked(o.id)
          ? 'border-primary-400 bg-primary-50 text-primary-700'
          : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'"
      >
        <input
          type="checkbox"
          :checked="isChecked(o.id)"
          @change="toggle(o.id)"
          class="h-3.5 w-3.5 rounded border-slate-300 text-primary-600 focus:ring-primary-400"
        />
        {{ o.label }}
      </label>
      <p v-if="field.options.length === 0" class="text-xs text-slate-400">
        该字段还没有配置选项，请先到分类的字段管理中添加。
      </p>
    </div>

    <!-- text / number / date -->
    <input
      v-else
      :type="inputType"
      :inputmode="field.type === 'number' ? 'decimal' : null"
      :step="field.type === 'number' ? 'any' : null"
      :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value)"
      :placeholder="field.type === 'date' ? null : `${field.name}（可选）`"
      :class="inputClass"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  field: { type: Object, required: true },
  modelValue: { type: [String, Number, Array, null], default: '' },
})
const emit = defineEmits(['update:modelValue'])

const inputClass =
  'w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 transition-colors focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100'

const inputType = computed(() => {
  if (props.field.type === 'number') return 'number'
  if (props.field.type === 'date') return 'date'
  return 'text'
})

function onSelect(event) {
  const raw = event.target.value
  emit('update:modelValue', raw === '' ? '' : Number(raw))
}

function isChecked(optionId) {
  return Array.isArray(props.modelValue) && props.modelValue.includes(optionId)
}

function toggle(optionId) {
  const next = Array.isArray(props.modelValue) ? [...props.modelValue] : []
  const index = next.indexOf(optionId)
  if (index === -1) next.push(optionId)
  else next.splice(index, 1)
  emit('update:modelValue', next)
}
</script>
```

- [ ] **Step 2: 改 LogForm 模板**

在 `frontend/src/views/LogForm.vue` 中：

删除整个「Wire」区块（`<!-- Wire -->` 注释及其后的 `<div>...</div>`，原文件第 51-59 行）。

在「External link」区块之后、「Image upload」区块之前插入：

```html
      <!-- Custom fields -->
      <DynamicField
        v-for="f in fields"
        :key="f.id"
        :field="f"
        v-model="fieldValues[f.id]"
      />
```

- [ ] **Step 3: 改 LogForm 脚本**

import 增加 `watch` 与组件：

```js
import { ref, computed, onMounted, watch } from 'vue'
import DynamicField from '../components/DynamicField.vue'
```

把 `form` 的初始值中的 `wire: '',` 删掉，并在 `form` 声明之后追加：

```js
const fields = ref([])
const fieldValues = ref({})
// 编辑模式下先把已有值暂存在这里，等分类的字段定义拉回来后再套用
let pendingValues = null

function defaultValue(field) {
  return field.type === 'multiselect' ? [] : ''
}

function buildValueMap(fieldList, existing) {
  const map = {}
  for (const f of fieldList) {
    map[f.id] = f.id in existing ? existing[f.id] : defaultValue(f)
  }
  return map
}

function valuesFromLog(log) {
  const map = {}
  for (const fv of log.field_values || []) {
    map[fv.field_id] = fv.value === null || fv.value === undefined
      ? (fv.type === 'multiselect' ? [] : '')
      : fv.value
  }
  return map
}

watch(() => form.value.category_id, async (cid) => {
  if (!cid) {
    fields.value = []
    fieldValues.value = {}
    pendingValues = null
    return
  }
  fields.value = await api.getCategoryFields(cid)
  // 切换分类时清空已填的自定义值，避免跨分类的脏数据
  fieldValues.value = buildValueMap(fields.value, pendingValues || {})
  pendingValues = null
})
```

把 `onMounted` 换成（注意：`pendingValues` 必须在赋值 `category_id` **之前**设好，
否则 watch 回调会用空对象初始化）：

```js
onMounted(async () => {
  categories.value = await api.getCategories()
  if (isEdit.value) {
    const log = await api.getLog(route.params.id)
    pendingValues = valuesFromLog(log)
    form.value.description = log.description
    form.value.external_link = log.external_link
    form.value.category_id = log.category_id
  }
})
```

把 `submit` 换成：

```js
function collectFieldValues() {
  const out = {}
  for (const f of fields.value) {
    out[String(f.id)] = fieldValues.value[f.id]
  }
  return out
}

function firstMissingRequired() {
  for (const f of fields.value) {
    if (!f.required) continue
    const v = fieldValues.value[f.id]
    const empty = v === '' || v === null || v === undefined || (Array.isArray(v) && v.length === 0)
    if (empty) return f
  }
  return null
}

async function submit() {
  if (!form.value.category_id) return alert('请选择分类')
  const missing = firstMissingRequired()
  if (missing) return alert(`字段「${missing.name}」为必填`)

  submitting.value = true
  try {
    if (isEdit.value) {
      await api.updateLog(route.params.id, {
        category_id: form.value.category_id,
        description: form.value.description,
        external_link: form.value.external_link,
        field_values: collectFieldValues(),
      })
      router.push(`/logs/${route.params.id}`)
    } else {
      const fd = new FormData()
      fd.append('category_id', form.value.category_id)
      fd.append('description', form.value.description)
      fd.append('external_link', form.value.external_link)
      fd.append('field_values', JSON.stringify(collectFieldValues()))
      for (const f of files.value) {
        fd.append('files', f)
      }
      const log = await api.createLog(fd)
      router.push(`/logs/${log.id}`)
    }
  } catch (e) {
    alert(e.message)
  } finally {
    submitting.value = false
  }
}
```

- [ ] **Step 4: 构建验证**

```bash
cd frontend && npm run build
```

- [ ] **Step 5: 手工验证**

1. 新建日志 → 未选分类时看不到任何自定义字段
2. 选「欢欢衣服」→ 品牌（下拉）、衣服类型（多选复选框）、购入价格（数字）、购入日期（日期）依次按排序出现
3. 点「购入日期」输入框 → 弹出系统日历（手机浏览器或 Chrome DevTools 移动模拟下验证）
4. 填完保存 → 跳到详情页，值正确
5. 编辑该日志 → 所有自定义字段回填正确，多选的已选项高亮
6. 编辑时把分类从「欢欢衣服」改成「手套」→ 字段整组换成手套的「线材」，之前填的衣服字段值被清空
7. 把某字段设为必填后留空提交 → 弹出「字段「X」为必填」且不提交

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/DynamicField.vue frontend/src/views/LogForm.vue
git commit -m "Render category fields dynamically in the log form"
```

---

### Task 14: 日志详情渲染自定义字段

**Files:**
- Modify: `frontend/src/views/LogDetail.vue`

**Interfaces:**
- Consumes: Task 6 的 `LogOut.field_values`
- Produces: 无

- [ ] **Step 1: 替换线材展示块**

在 `frontend/src/views/LogDetail.vue` 中，把整个「Wire」区块（`<!-- Wire -->` 注释及其后的 `<div>...</div>`，原文件第 104-108 行）替换为：

```html
      <!-- Custom fields -->
      <div v-for="fv in log.field_values" :key="fv.field_id" class="px-5 py-3.5">
        <p class="mb-0.5 text-xs font-medium text-slate-400">{{ fv.name }}</p>
        <div v-if="fv.type === 'select' || fv.type === 'multiselect'" class="flex flex-wrap gap-1.5">
          <span
            v-for="label in fv.option_labels"
            :key="label"
            class="inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700"
          >
            {{ label }}
          </span>
        </div>
        <p v-else class="whitespace-pre-wrap text-sm text-slate-700">{{ fv.value }}</p>
      </div>
```

> 后端不会为空值返回行，因此这里不需要额外的 `v-if` 判空，
> 行为与原来的 `v-if="log.wire"` 一致。

- [ ] **Step 2: 构建验证**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: 手工验证**

1. 打开一条填了自定义字段的「欢欢衣服」日志 → 描述、外部链接之后按字段排序显示各字段
2. 多选字段显示成多个灰色 pill
3. 空着没填的字段完全不显示
4. 打开迁移过来的那条「手套」日志 → 显示「线材」及其原值
5. 到字段管理里把「品牌」的选项 Nike 改名 → 刷新详情页，显示的是新名字

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/LogDetail.vue
git commit -m "Render custom field values on the log detail page"
```

---

### Task 15: 列表卡片显示 show_in_list 字段

**Files:**
- Modify: `frontend/src/views/LogList.vue`

**Interfaces:**
- Consumes: Task 9 的列表端点（只返回 `show_in_list` 字段值）
- Produces: `LogList.cardValue(fv) -> string`

- [ ] **Step 1: 在卡片上插入字段区块**

在 `frontend/src/views/LogList.vue` 中，「Description」区块之后、「Date」区块之前插入：

```html
          <!-- Custom fields on card -->
          <div v-if="log.field_values && log.field_values.length" class="mb-1.5 space-y-0.5">
            <div
              v-for="fv in log.field_values"
              :key="fv.field_id"
              class="flex items-baseline gap-1.5 text-[10px] leading-tight"
            >
              <span class="shrink-0 text-slate-400">{{ fv.name }}</span>
              <span class="min-w-0 flex-1 truncate text-slate-600">{{ cardValue(fv) }}</span>
            </div>
          </div>
```

- [ ] **Step 2: 加 cardValue 方法**

在 `LogList.vue` 的 `<script setup>` 中，`formatDate` 附近追加：

```js
function cardValue(fv) {
  if (fv.type === 'select') {
    return fv.option_labels[0] || ''
  }
  if (fv.type === 'multiselect') {
    const labels = fv.option_labels || []
    if (labels.length <= 2) return labels.join('、')
    return `${labels.slice(0, 2).join('、')} +${labels.length - 2}`
  }
  return fv.value
}
```

- [ ] **Step 3: 构建验证**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: 手工验证**

1. 在字段管理里把「品牌」和「购入价格」勾选「显示在列表卡片」
2. 回到列表页 → 衣服类日志的卡片上，描述下方出现「品牌 NIKE」「购入价格 899」两行
3. 把「衣服类型」（多选）也勾上，并给某条日志勾选 3 个以上选项 → 卡片显示「外套、卫衣 +1」
4. 取消所有 `show_in_list` → 卡片恢复成原来的样子（封面图、分类、状态、描述、日期）
5. 用 Chrome DevTools 切到 iPhone SE 宽度（375px）→ 卡片不溢出，长值单行截断

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/LogList.vue
git commit -m "Show flagged custom fields on log list cards"
```

---

### Task 16: 列表页筛选与排序控件

**Files:**
- Modify: `frontend/src/views/LogList.vue`

**Interfaces:**
- Consumes: Task 8 的 `fv` 与 `sort` 查询参数；Task 10 的 `api.getCategoryFields` 与数组参数支持
- Produces: 无

- [ ] **Step 1: 在筛选区下方加控件**

在 `frontend/src/views/LogList.vue` 的「Filter pills」那个 `<div>` 闭合之后、「Loading」区块之前插入：

```html
    <!-- Custom field filters (only when a single category is selected) -->
    <div v-if="activeFields.length" class="mb-4 space-y-2">
      <div
        v-for="f in optionFields"
        :key="f.id"
        class="flex gap-2 overflow-x-auto hide-scrollbar pb-0.5"
      >
        <span class="shrink-0 self-center text-[11px] font-medium text-slate-400">{{ f.name }}</span>
        <button
          v-for="o in f.options"
          :key="o.id"
          @click="toggleOption(f.id, o.id)"
          class="shrink-0 rounded-full px-3 py-1 text-xs font-medium transition-colors"
          :class="isOptionSelected(f.id, o.id)
            ? 'bg-slate-900 text-white shadow-sm'
            : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'"
        >
          {{ o.label }}
        </button>
      </div>

      <div v-if="sortableFields.length" class="flex items-center gap-2">
        <span class="shrink-0 text-[11px] font-medium text-slate-400">排序</span>
        <select
          v-model="sortValue"
          @change="page = 1; load()"
          class="rounded-xl border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        >
          <option value="">最新创建</option>
          <template v-for="f in sortableFields" :key="f.id">
            <option :value="`${f.id}:desc`">{{ f.name }} 从高到低</option>
            <option :value="`${f.id}:asc`">{{ f.name }} 从低到高</option>
          </template>
        </select>
      </div>
    </div>
```

- [ ] **Step 2: 加状态与方法**

`LogList.vue` 的 `<script setup>` 中，import 补 `computed` 与 `watch`：

```js
import { ref, computed, onMounted, watch } from 'vue'
```

在 `filterStatus` 声明之后追加：

```js
const activeFields = ref([])
const selectedOptions = ref({})
const sortValue = ref('')

const optionFields = computed(() =>
  activeFields.value.filter(
    (f) => (f.type === 'select' || f.type === 'multiselect') && f.options.length > 0
  )
)
const sortableFields = computed(() =>
  activeFields.value.filter((f) => f.type === 'number' || f.type === 'date')
)

watch(filterCategory, async (cid) => {
  // 换分类就把该分类专属的筛选条件全部重置
  selectedOptions.value = {}
  sortValue.value = ''
  activeFields.value = cid ? await api.getCategoryFields(cid) : []
})

function isOptionSelected(fieldId, optionId) {
  return (selectedOptions.value[fieldId] || []).includes(optionId)
}

function toggleOption(fieldId, optionId) {
  const current = [...(selectedOptions.value[fieldId] || [])]
  const index = current.indexOf(optionId)
  if (index === -1) current.push(optionId)
  else current.splice(index, 1)

  if (current.length === 0) {
    const next = { ...selectedOptions.value }
    delete next[fieldId]
    selectedOptions.value = next
  } else {
    selectedOptions.value = { ...selectedOptions.value, [fieldId]: current }
  }
  page.value = 1
  load()
}

function buildFvParams() {
  const out = []
  for (const [fieldId, optionIds] of Object.entries(selectedOptions.value)) {
    for (const optionId of optionIds) out.push(`${fieldId}:${optionId}`)
  }
  return out
}
```

在 `load()` 中，把传给 `api.getLogs` 的参数对象补上两个键：

```js
    fv: buildFvParams(),
    sort: sortValue.value,
```

> `api.getLogs` 会跳过空字符串与空数组，所以未筛选时不会污染 URL。

- [ ] **Step 3: 构建验证**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: 手工验证**

前置：在「欢欢衣服」下建好至少 3 条日志，品牌分别为 NIKE / Adidas / Uniqlo，
其中两条的「衣服类型」包含「外套」，价格分别填 899 / 499 / 留空。

1. 列表页选「全部」分类 → **不显示**任何自定义字段筛选器
2. 选「欢欢衣服」→ 出现「品牌」「衣服类型」两行筛选 pill 和排序下拉
3. 点「NIKE」→ 只剩 NIKE 那条
4. 再点「Adidas」（同字段第二个）→ NIKE 和 Adidas 两条都在（同字段 OR）
5. 保持上面两个选中，再点「衣服类型 → 外套」→ 结果进一步收窄（跨字段 AND）
6. 排序选「购入价格 从高到低」→ 899、499、然后是价格留空的那条排最后
7. 切到「手套」分类 → 筛选条件全部重置，显示手套自己的字段（线材是文本类型，
   不可筛选也不可排序，所以筛选区为空）
8. 切回「全部」→ 筛选器消失，列表显示所有日志

- [ ] **Step 5: 全量回归**

```bash
cd backend && .venv/bin/pytest tests -v
cd ../frontend && npm run build
```

预期：51 passed；build 成功。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/LogList.vue
git commit -m "Add custom field filters and sorting to the log list"
```

---

## 上线前检查

实现完成后、部署到 NAS 之前：

- [ ] `cd backend && .venv/bin/pytest tests -v` → 51 passed
- [ ] `cd frontend && npm run build` → 成功
- [ ] `grep -rniE "bemine|goblin\.top|192\.168" frontend/src backend` → 无输出（不得引入硬编码地址）
- [ ] `grep -rn "wire" backend/routers backend/models.py` → 只有 `database.py` 的迁移代码提及 wire，路由与模型中不得残留
- [ ] 用生产库的副本演练一次迁移：
  ```bash
  scp root@192.168.8.10:/volume2/homes/darlingz/pic/data/piclog.db /tmp/piclog-copy.db
  cd backend && DB_PATH=/tmp/piclog-copy.db .venv/bin/python -c "import database; database.init_db(); database.init_db()"
  sqlite3 /tmp/piclog-copy.db "SELECT f.name, v.value_text FROM log_field_values v JOIN category_fields f ON f.id = v.field_id;"
  ```
  预期输出一行：`线材|<原值>`
