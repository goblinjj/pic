# 只读分享链接 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户可以把某个分类或整个账号生成只读分享链接，访客无需登录即可浏览、搜索、筛选、以图搜图。

**Architecture:** `accounts.db` 新增 `shares` 表；主人侧 `/api/shares` 管理链接；访客侧独立路由 `/api/share/{token}/...`
只有读接口和以图搜图，经 `deps.share_scope` 解析 token 并在每条查询上强制拼接范围条件。前端把
`LogList` / `LogDetail` / `ImageSearch` / `LogCard` / `CameraSearchButton` 改为从注入的「数据源」取数据，
分享页 `/s/:token` 注入只读数据源复用这些组件。

**Tech Stack:** FastAPI + SQLite（每账号一个库）、pytest + TestClient；Vue 3 `<script setup>` + vue-router 4 + Tailwind 4，Vite 构建。

**Spec:** `docs/superpowers/specs/2026-10-08-share-links-design.md`

## Global Constraints

- 后端测试：在 `backend/` 下运行 `.venv/bin/python -m pytest -q`；当前基线 243 passed, 1 skipped，任何任务结束时现有测试必须全部通过
- 前端没有测试框架，不引入；前端任务以 `cd frontend && npm run build` 成功 + 手动验证为准
- token：`secrets.token_urlsafe(24)`，明文存储
- 访客侧所有失败统一 `404 "分享链接不存在或已失效"`，不区分原因
- 访客侧 `/logs`：`page ≥ 1`、`1 ≤ size ≤ 100`，越界 422
- 以图搜图限流：key `("share_search", ip)`，每 IP 每 60 秒 10 次，超出 `429 "搜索太频繁，请稍后再试"`；只放进程内存
- 访客侧以图搜图返回 `pending` 固定为 0
- 分享路径下不存在 PUT / PATCH / DELETE，POST 只有 `/search/image`
- 访客侧依赖不读取 Cookie；分享页前端请求不带 `X-PicLog-User`，401/404 不跳登录页
- 代码注释用中文，风格与周边代码一致（解释「为什么」）；提交信息用英文祈使句（与 git log 一致），结尾加
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
- 不要 `git push`：pre-push hook 会部署到 NAS

## Review Focus

1. 访客用 `..%2Fpiclog.db` 一类的文件名请求分享下的图片 → 必须 404，不能读到库文件（Task 4 测试 `test_file_path_traversal_404`）
2. 访客浏览器里正登录着另一个账号 B，打开 A 的分享 → 看到的必须是 A 的数据，且 B 的 Cookie 不影响结果（Task 4 `test_other_account_cookie_does_not_matter`）
3. 匿名请求 `size=100000` 或 `page=0` → 422，不能一次拉全库或产生负 offset（Task 4 `test_logs_page_and_size_bounds`）
4. 分类被改名后，分享页标题显示新名字（`/info` 实时读名称，Task 4 `test_info_reflects_category_rename`）
5. 账号停用后链接失效，重新启用后同一链接恢复可用（链接没被删，Task 4 `test_disabled_then_reenabled_account`）

---

## File Structure

后端：

| 文件 | 动作 | 职责 |
| --- | --- | --- |
| `backend/accounts.py` | 改 | `shares` 表结构 + 增删查函数 |
| `backend/models.py` | 改 | `ShareCreate`、`ShareOut`、`ShareInfoOut` |
| `backend/routers/shares.py` | 新 | 主人侧 `/api/shares` |
| `backend/routers/categories.py` | 改 | 删除分类时删其分享 |
| `backend/routers/logs.py` | 改 | 抽出 `query_logs()`，`list_logs` 改调它 |
| `backend/image_search.py` | 改 | `rank_logs` 加 `category_id` |
| `backend/routers/search.py` | 改 | 抽出 `run_image_search()` |
| `backend/ratelimit.py` | 改 | 新增滑动窗口 `hit()` |
| `backend/deps.py` | 改 | `ShareScope`、`share_scope` |
| `backend/routers/public_share.py` | 新 | 访客侧 `/api/share/{token}/...` |
| `backend/main.py` | 改 | 注册两个新路由 |
| `backend/tests/test_accounts.py` | 改 | 分享函数单测 |
| `backend/tests/test_shares.py` | 新 | 主人侧接口 |
| `backend/tests/test_share_access.py` | 新 | 访客侧接口与隔离 |
| `backend/tests/test_ratelimit.py` | 新 | `hit()` 单测 |
| `backend/tests/test_image_search.py` | 改 | `rank_logs` 分类过滤 |

前端：

| 文件 | 动作 | 职责 |
| --- | --- | --- |
| `frontend/src/thumbs.js` | 改 | `thumbUrl` / `fileUrl` 接受 base |
| `frontend/src/imageSearch.js` | 改 | 模块单例改为工厂 `createImageSearch` |
| `frontend/src/api.js` | 改 | 导出 `formatDetail`、`toQuery`；分享管理接口 |
| `frontend/src/source.js` | 新 | 主人侧数据源 `ownerSource`、`useSource()` |
| `frontend/src/shareApi.js` | 新 | `createShareSource(token)` |
| `frontend/src/shareLink.js` | 新 | `shareUrl`、`copyText` |
| `frontend/src/components/LogCard.vue` | 改 | 用数据源 |
| `frontend/src/components/CameraSearchButton.vue` | 改 | 用数据源 |
| `frontend/src/views/LogList.vue` | 改 | 用数据源；只读；锁定分类 |
| `frontend/src/views/LogDetail.vue` | 改 | 用数据源；只读 |
| `frontend/src/views/ImageSearch.vue` | 改 | 用数据源 |
| `frontend/src/views/ShareLayout.vue` | 新 | 分享页外壳、失效页 |
| `frontend/src/components/ShareLinkField.vue` | 新 | 链接输入框 + 复制 |
| `frontend/src/views/Shares.vue` | 新 | 我的分享 |
| `frontend/src/views/Categories.vue` | 改 | 分享按钮、弹窗、入口 |
| `frontend/src/router.js` | 改 | 分享路由、`/shares`、守卫 |

---

### Task 1: `shares` 表与账号库函数

**Files:**
- Modify: `backend/accounts.py`（`init_schema` 内追加建表；文件末尾追加「分享」一节）
- Test: `backend/tests/test_accounts.py`（文件末尾追加）

**Interfaces:**
- Produces:
  - `accounts.create_share(conn, user_id: int, category_id: int | None) -> str`
  - `accounts.get_share(conn, user_id: int, token: str) -> sqlite3.Row | None`（列：`token, user_id, category_id, created_at`）
  - `accounts.list_shares(conn, user_id: int) -> list[sqlite3.Row]`（同上列，新的在前）
  - `accounts.delete_share(conn, user_id: int, token: str) -> bool`
  - `accounts.delete_shares_for_category(conn, user_id: int, category_id: int) -> None`
  - `accounts.resolve_share(conn, token: str) -> sqlite3.Row | None`（列：`token, user_id, category_id, username`；账号停用返回 None）

- [ ] **Step 1: 写失败的测试**

追加到 `backend/tests/test_accounts.py` 末尾（该文件已有 `conn` fixture，建在临时目录）：

```python
# ------------------------------------------------------------------ 分享

def test_share_create_list_resolve(conn):
    uid = accounts.create_user(conn, "alice", "password-1")
    t_all = accounts.create_share(conn, uid, None)
    t_cat = accounts.create_share(conn, uid, 7)
    assert t_all != t_cat and len(t_all) == 32

    rows = accounts.list_shares(conn, uid)
    # 新的在前
    assert [r["token"] for r in rows] == [t_cat, t_all]
    assert [r["category_id"] for r in rows] == [7, None]

    hit = accounts.resolve_share(conn, t_cat)
    assert (hit["user_id"], hit["category_id"], hit["username"]) == (uid, 7, "alice")
    assert accounts.get_share(conn, uid, t_all)["category_id"] is None


def test_share_resolve_unknown_or_empty(conn):
    assert accounts.resolve_share(conn, "") is None
    assert accounts.resolve_share(conn, "nope") is None


def test_share_delete_only_own(conn):
    a = accounts.create_user(conn, "alice", "password-1")
    b = accounts.create_user(conn, "bob", "password-1")
    token = accounts.create_share(conn, a, None)
    assert accounts.delete_share(conn, b, token) is False
    assert accounts.resolve_share(conn, token) is not None
    assert accounts.get_share(conn, b, token) is None
    assert accounts.delete_share(conn, a, token) is True
    assert accounts.resolve_share(conn, token) is None


def test_share_delete_for_category_scoped_to_user(conn):
    a = accounts.create_user(conn, "alice", "password-1")
    b = accounts.create_user(conn, "bob", "password-1")
    ta = accounts.create_share(conn, a, 1)
    tb = accounts.create_share(conn, b, 1)   # 各账号的分类 id 都从 1 开始
    t_all = accounts.create_share(conn, a, None)
    accounts.delete_shares_for_category(conn, a, 1)
    assert accounts.resolve_share(conn, ta) is None
    assert accounts.resolve_share(conn, tb) is not None
    assert accounts.resolve_share(conn, t_all) is not None


def test_share_inactive_user_not_resolved(conn):
    uid = accounts.create_user(conn, "alice", "password-1")
    token = accounts.create_share(conn, uid, None)
    accounts.set_active(conn, uid, False)
    assert accounts.resolve_share(conn, token) is None
    accounts.set_active(conn, uid, True)
    assert accounts.resolve_share(conn, token) is not None
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_accounts.py -q -k share`
Expected: FAIL，`AttributeError: module 'accounts' has no attribute 'create_share'`

- [ ] **Step 3: 实现**

在 `accounts.init_schema` 的 `executescript` 里、`meta` 表之后追加：

```sql
        -- 只读分享链接。token 明文存：用户要在「我的分享」里随时复制已有链接；
        -- 能读到本库的人本来就能读到同目录下所有账号的库，哈希不多保护什么
        CREATE TABLE IF NOT EXISTS shares (
            token       TEXT PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            category_id INTEGER,          -- NULL = 整个账号；指向该账号自己库里的分类，跨库无外键
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_shares_user ON shares(user_id);
```

在文件末尾（`get_meta` / `set_meta` 之后）追加：

```python
# ------------------------------------------------------------------ 分享

_SHARE_COLUMNS = "token, user_id, category_id, created_at"


def create_share(conn, user_id: int, category_id: Optional[int]) -> str:
    token = secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO shares (token, user_id, category_id) VALUES (?, ?, ?)",
        (token, user_id, category_id),
    )
    conn.commit()
    return token


def get_share(conn, user_id: int, token: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        f"SELECT {_SHARE_COLUMNS} FROM shares WHERE token = ? AND user_id = ?",
        (token, user_id),
    ).fetchone()


def list_shares(conn, user_id: int) -> list[sqlite3.Row]:
    # created_at 只精确到秒，同一秒建的按插入顺序
    return conn.execute(
        f"SELECT {_SHARE_COLUMNS} FROM shares WHERE user_id = ? "
        "ORDER BY created_at DESC, rowid DESC",
        (user_id,),
    ).fetchall()


def delete_share(conn, user_id: int, token: str) -> bool:
    cur = conn.execute("DELETE FROM shares WHERE token = ? AND user_id = ?", (token, user_id))
    conn.commit()
    return cur.rowcount > 0


def delete_shares_for_category(conn, user_id: int, category_id: int):
    conn.execute(
        "DELETE FROM shares WHERE user_id = ? AND category_id = ?", (user_id, category_id)
    )
    conn.commit()


def resolve_share(conn, token: str) -> Optional[sqlite3.Row]:
    """访客打开链接时用：账号停用的分享视为无效（不删，重新启用后恢复）。"""
    if not token:
        return None
    return conn.execute(
        "SELECT s.token, s.user_id, s.category_id, u.username "
        "FROM shares s JOIN users u ON u.id = s.user_id "
        "WHERE s.token = ? AND u.is_active = 1",
        (token,),
    ).fetchone()
```

- [ ] **Step 4: 运行，确认通过**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 全部通过（243 + 5 新增）

- [ ] **Step 5: 提交**

```bash
git add backend/accounts.py backend/tests/test_accounts.py
git commit -m "Add shares table and account-level share functions"
```

---

### Task 2: 主人侧 `/api/shares` 与删除分类联动

**Files:**
- Modify: `backend/models.py`（末尾追加）
- Create: `backend/routers/shares.py`
- Modify: `backend/routers/categories.py`（`delete_category`）
- Modify: `backend/main.py`（import 与 `include_router`）
- Test: `backend/tests/test_shares.py`

**Interfaces:**
- Consumes: Task 1 的 `accounts.create_share / get_share / list_shares / delete_share / delete_shares_for_category`
- Produces:
  - `models.ShareCreate(category_id: Optional[int] = None)`
  - `models.ShareOut(token: str, category_id: Optional[int], category_name: str, created_at: str)`
  - `models.ShareInfoOut(scope: str, category_id: Optional[int], category_name: str, owner: str)`（Task 4 用）
  - HTTP：`GET /api/shares`、`POST /api/shares`（201）、`DELETE /api/shares/{token}`（204）

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_shares.py`：

```python
"""主人侧分享管理：创建、列出、撤销，以及删除分类时联动。"""
import accounts


def _cat(client, name="手套"):
    return client.post("/api/categories", json={"name": name}).json()["id"]


def test_create_account_and_category_shares(client):
    cid = _cat(client)
    whole = client.post("/api/shares", json={"category_id": None})
    assert whole.status_code == 201, whole.text
    assert whole.json()["category_id"] is None
    assert whole.json()["category_name"] == ""
    assert len(whole.json()["token"]) == 32

    one = client.post("/api/shares", json={"category_id": cid}).json()
    assert (one["category_id"], one["category_name"]) == (cid, "手套")

    listed = client.get("/api/shares").json()
    assert [s["token"] for s in listed] == [one["token"], whole.json()["token"]]


def test_body_may_omit_category_id(client):
    resp = client.post("/api/shares", json={})
    assert resp.status_code == 201
    assert resp.json()["category_id"] is None


def test_create_with_unknown_category_400(client):
    resp = client.post("/api/shares", json={"category_id": 999})
    assert resp.status_code == 400
    assert client.get("/api/shares").json() == []


def test_list_only_own(client, make_user):
    client.post("/api/shares", json={})
    bob = make_user("bob")
    assert bob.get("/api/shares").json() == []


def test_revoke(client):
    token = client.post("/api/shares", json={}).json()["token"]
    assert client.delete(f"/api/shares/{token}").status_code == 204
    assert client.get("/api/shares").json() == []
    assert client.delete(f"/api/shares/{token}").status_code == 404


def test_cannot_revoke_others(client, make_user):
    token = client.post("/api/shares", json={}).json()["token"]
    bob = make_user("bob")
    assert bob.delete(f"/api/shares/{token}").status_code == 404
    assert len(client.get("/api/shares").json()) == 1


def test_deleting_category_removes_its_shares(client):
    keep = _cat(client, "保留")
    gone = _cat(client, "删除")
    t_keep = client.post("/api/shares", json={"category_id": keep}).json()["token"]
    client.post("/api/shares", json={"category_id": gone})
    t_all = client.post("/api/shares", json={}).json()["token"]

    assert client.delete(f"/api/categories/{gone}").status_code == 204
    assert {s["token"] for s in client.get("/api/shares").json()} == {t_keep, t_all}


def test_category_name_empty_when_category_missing(client):
    """分类直接从库里没了（比如手工改库）也照样列出，方便撤销。"""
    cid = _cat(client)
    conn = accounts.connect()
    accounts.create_share(conn, 1, cid + 100)
    conn.close()
    names = [s["category_name"] for s in client.get("/api/shares").json()]
    assert names == [""]


def test_requires_login(anon_client):
    assert anon_client.get("/api/shares").status_code == 401
    assert anon_client.post("/api/shares", json={}).status_code == 401
    assert anon_client.delete("/api/shares/x").status_code == 401
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_shares.py -q`
Expected: FAIL，`/api/shares` 返回 404/405

- [ ] **Step 3: 实现**

`backend/models.py` 末尾追加：

```python
class ShareCreate(BaseModel):
    # None = 分享整个账号
    category_id: Optional[int] = None


class ShareOut(BaseModel):
    token: str
    category_id: Optional[int]
    category_name: str = ""
    created_at: str


class ShareInfoOut(BaseModel):
    scope: str                 # "account" | "category"
    category_id: Optional[int]
    category_name: str = ""
    owner: str
```

`backend/routers/shares.py`：

```python
"""主人侧：管理自己的只读分享链接。访客侧见 public_share.py。"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

import accounts
from deps import current_user_id, get_db
from models import ShareCreate, ShareOut

router = APIRouter(prefix="/api/shares", tags=["shares"])


def _category_names(db: sqlite3.Connection) -> dict[int, str]:
    return {r["id"]: r["name"] for r in db.execute("SELECT id, name FROM categories")}


def _out(row, names: dict[int, str]) -> dict:
    cid = row["category_id"]
    return {
        "token": row["token"],
        "category_id": cid,
        # 分类已不存在的照样列出，名称留空，好让用户撤销
        "category_name": names.get(cid, "") if cid is not None else "",
        "created_at": row["created_at"],
    }


@router.get("", response_model=list[ShareOut])
def list_shares(
    user_id: int = Depends(current_user_id),
    db: sqlite3.Connection = Depends(get_db),
):
    conn = accounts.connect()
    try:
        rows = accounts.list_shares(conn, user_id)
    finally:
        conn.close()
    names = _category_names(db)
    return [_out(r, names) for r in rows]


@router.post("", response_model=ShareOut, status_code=201)
def create_share(
    body: ShareCreate,
    user_id: int = Depends(current_user_id),
    db: sqlite3.Connection = Depends(get_db),
):
    if body.category_id is not None:
        exists = db.execute(
            "SELECT 1 FROM categories WHERE id = ?", (body.category_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(400, "分类不存在")
    conn = accounts.connect()
    try:
        token = accounts.create_share(conn, user_id, body.category_id)
        row = accounts.get_share(conn, user_id, token)
    finally:
        conn.close()
    return _out(row, _category_names(db))


@router.delete("/{token}", status_code=204)
def delete_share(token: str, user_id: int = Depends(current_user_id)):
    conn = accounts.connect()
    try:
        deleted = accounts.delete_share(conn, user_id, token)
    finally:
        conn.close()
    if not deleted:
        raise HTTPException(404, "分享不存在")
```

`backend/routers/categories.py`：import 改为

```python
from fastapi import APIRouter, Depends, HTTPException
import sqlite3
import accounts
from deps import current_user_id, get_db
from models import CategoryCreate, CategoryUpdate, CategoryOut
```

`delete_category` 改为：

```python
@router.delete("/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    db: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
):
    existing = db.execute(
        "SELECT id FROM categories WHERE id = ?", (category_id,)
    ).fetchone()
    if not existing:
        raise HTTPException(404, "Category not found")
    log_count = db.execute(
        "SELECT COUNT(*) as c FROM logs WHERE category_id = ?", (category_id,)
    ).fetchone()["c"]
    if log_count > 0:
        raise HTTPException(400, "Category has logs, cannot delete")
    db.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    db.commit()
    # 以后新建的分类可能复用这个 id（SQLite 无 AUTOINCREMENT 时会复用最大值），
    # 旧链接不能因此指向新分类
    conn = accounts.connect()
    try:
        accounts.delete_shares_for_category(conn, user_id, category_id)
    finally:
        conn.close()
```

（保留函数原有的其余部分不变；如果原函数末尾没有 return，也不要加。）

`backend/main.py`：

```python
from routers import auth, categories, logs, images, fields, search, files, shares
...
    app.include_router(files.router)
    app.include_router(shares.router)
```

- [ ] **Step 4: 运行，确认通过**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add backend/models.py backend/routers/shares.py backend/routers/categories.py backend/main.py backend/tests/test_shares.py
git commit -m "Add owner API for managing share links"
```

---

### Task 3: 抽出可复用的查询与以图搜图函数

纯重构 + `rank_logs` 新参数：主人侧行为不变，现有测试是回归保障。

**Files:**
- Modify: `backend/routers/logs.py`（`list_logs`）
- Modify: `backend/image_search.py`（`rank_logs`）
- Modify: `backend/routers/search.py`（`search_by_image`）
- Test: `backend/tests/test_image_search.py`（末尾追加）

**Interfaces:**
- Produces:
  - `routers.logs.query_logs(db, *, scope_where: list[str] = (), scope_params: list = (), search=None, category_id=None, status=None, fv=(), sort=None, page=1, size=20) -> dict`（返回 `{"items", "total", "page", "size"}`）
  - `image_search.rank_logs(db, query_vec, limit, min_score=MIN_SCORE, category_id: int | None = None)`
  - `routers.search.run_image_search(db, file: UploadFile, limit: int, min_score: float, category_id: int | None = None) -> tuple[list[dict], int]`（`(items, indexed)`）

- [ ] **Step 1: 写失败的测试**

追加到 `backend/tests/test_image_search.py`：

```python
def test_rank_logs_category_filter(client, gallery, db_conn):
    from image_search import rank_logs

    other = client.post("/api/categories", json={"name": "帽子"}).json()["id"]
    red_hat = make_log(client, other, "红帽子", png("h.png", RED))
    assert indexer.process_pending() == 1

    vec = mean_color_vector(Image.new("RGB", (8, 8), RED))
    all_hits, _ = rank_logs(db_conn, vec, limit=10)
    assert red_hat["id"] in [h.log_id for h in all_hits]

    hits, indexed = rank_logs(db_conn, vec, limit=10, category_id=other)
    assert [h.log_id for h in hits] == [red_hat["id"]]
    assert indexed == 1
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_image_search.py -q -k category_filter`
Expected: FAIL，`TypeError: rank_logs() got an unexpected keyword argument 'category_id'`

- [ ] **Step 3: 实现**

`backend/image_search.py` 的 `rank_logs` 改为：

```python
def rank_logs(
    db, query_vec, limit: int, min_score: float = MIN_SCORE, category_id: Optional[int] = None,
) -> tuple[list[Hit], int]:
    """返回 (按分数降序的命中列表, 参与比对的向量数)。

    每条日志只出现一次，分数取它所有图片中的最高分，image_id 是那张图。
    category_id 非空时只在该分类内比对（分类级分享）。
    """
    sql = """
        SELECT e.image_id, e.vector, i.log_id
        FROM image_embeddings e
        JOIN images i ON i.id = e.image_id
        JOIN logs l ON l.id = i.log_id
        WHERE l.deleted_at IS NULL AND e.model = ?
    """
    params: list = [embedding.MODEL_ID]
    if category_id is not None:
        sql += " AND l.category_id = ?"
        params.append(category_id)
    rows = db.execute(sql, params).fetchall()
    # ……其余保持不变
```

文件顶部加 `from typing import NamedTuple, Optional`（替换原来的 `from typing import NamedTuple`）。

`backend/routers/logs.py`：把 `list_logs` 的函数体抽成 `query_logs`，放在 `list_logs` 之前：

```python
def query_logs(
    db: sqlite3.Connection,
    *,
    scope_where=(),
    scope_params=(),
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    status: Optional[str] = None,
    fv=(),
    sort: Optional[str] = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    """列表查询。scope_where/scope_params 由分享接口传入，与筛选条件 AND。"""
    where, params = ["l.deleted_at IS NULL", *scope_where], list(scope_params)
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

    items = _build_log_list(db, rows)
    return {"items": items, "total": total, "page": page, "size": size}


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
    return query_logs(
        db, search=search, category_id=category_id, status=status,
        fv=fv, sort=sort, page=page, size=size,
    )
```

注意 `scope_where` 的条件里引用的是别名 `l`，`build_sort` 的 JOIN 用的也是 `l`，两者兼容。

`backend/routers/search.py`：把 `search_by_image` 中「读文件 → 推理 → 排序 → 组装」抽出：

```python
def run_image_search(
    db: sqlite3.Connection,
    file: UploadFile,
    limit: int,
    min_score: float,
    category_id: Optional[int] = None,
) -> tuple[list[dict], int]:
    """返回 (命中列表, 参与比对的向量数)。主人侧与分享侧共用。"""
    if not embedding.available():
        raise HTTPException(503, "以图搜图未启用")
    content = file.file.read(MAX_QUERY_BYTES + 1)
    if len(content) > MAX_QUERY_BYTES:
        raise HTTPException(413, "图片文件过大")
    query_img = _load_query_image(content)
    try:
        vec = embedding.embed(query_img)
    except embedding.EmbeddingUnavailable:
        raise HTTPException(503, "以图搜图未启用")

    hits, indexed = rank_logs(db, vec, limit=limit, min_score=min_score, category_id=category_id)

    items = []
    if hits:
        ids = [h.log_id for h in hits]
        placeholders = ",".join("?" * len(ids))
        rows = db.execute(
            f"SELECT {LOG_COLUMNS} FROM logs l WHERE l.id IN ({placeholders})", ids
        ).fetchall()
        logs_by_id = {log["id"]: log for log in _build_log_list(db, rows)}
        for hit in hits:
            log = logs_by_id.get(hit.log_id)
            image = next((i for i in log["images"] if i["id"] == hit.image_id), None) if log else None
            if image is None:
                continue
            items.append({"log": log, "score": round(hit.score, 4), "matched_image": image})
    return items, indexed


# 同步函数：FastAPI 会放到线程池里跑，几秒的推理不会卡住事件循环
@router.post("/api/search/image", response_model=ImageSearchOut)
def search_by_image(
    file: UploadFile = File(...),
    limit: int = Query(20, ge=1, le=50),
    # 评测脚本传 -1 取回全部分数；前端不传
    min_score: float = Query(MIN_SCORE, ge=-1.0, le=1.0),
    db: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
):
    items, indexed = run_image_search(db, file, limit, min_score)
    return {"items": items, "indexed": indexed, "pending": indexer.count_pending(db, user_id)}
```

顶部加 `from typing import Optional`。

- [ ] **Step 4: 运行，确认通过**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add backend/routers/logs.py backend/image_search.py backend/routers/search.py backend/tests/test_image_search.py
git commit -m "Extract reusable log query and image search helpers"
```

---

### Task 4: 访客侧只读接口

**Files:**
- Modify: `backend/deps.py`（末尾追加）
- Create: `backend/routers/public_share.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_share_access.py`

**Interfaces:**
- Consumes: `accounts.resolve_share`、`accounts.set_active`（Task 1）；`models.ShareInfoOut`（Task 2）；`query_logs`（Task 3）；`routers.logs.LOG_COLUMNS / _build_log`；`routers.fields.FIELD_COLUMNS / _field_row_to_dict`；`routers.files.CACHE_HEADERS`；`thumbnail.thumb_dir`
- Produces:
  - `deps.ShareScope(user_id, username, category_id, category_name, db, upload_dir)`、`deps.share_scope(token)`、`deps.SHARE_NOT_FOUND`
  - `routers.public_share.router`（prefix `/api/share/{token}`）、`routers.public_share.scope_clause(scope) -> tuple[list[str], list]`
  - HTTP（全部 GET）：`/info`、`/categories`、`/categories/{cid}/fields`、`/logs`、`/logs/{id}`、`/files/{filename}`、`/files/thumbs/{filename}`

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_share_access.py`：

```python
"""访客侧分享接口：不登录能读，且严格限定在分享范围内。"""
import pytest
from fastapi.testclient import TestClient

import accounts
import indexer
from main import app
from tests.helpers import BLUE, RED, solid_image_bytes


@pytest.fixture(autouse=True)
def clean_indexer_state():
    indexer.reset_state()
    yield
    indexer.reset_state()


def _log(client, cid, desc, color=RED, **extra):
    resp = client.post(
        "/api/logs",
        data={"category_id": cid, "description": desc, **extra},
        files=[("files", ("a.png", solid_image_bytes(color), "image/png"))],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def data(client):
    """1 号账号：手套（带 select 字段）两条、帽子一条、手套里一条已删除。"""
    gloves = client.post("/api/categories", json={"name": "手套"}).json()["id"]
    hats = client.post("/api/categories", json={"name": "帽子"}).json()["id"]
    field = client.post(
        f"/api/categories/{gloves}/fields", json={"name": "颜色", "type": "select"}
    ).json()
    client.post(f"/api/fields/{field['id']}/options", json={"label": "红"})
    g1 = _log(client, gloves, "红手套")
    g2 = _log(client, gloves, "蓝手套", BLUE)
    h1 = _log(client, hats, "红帽子")
    gone = _log(client, gloves, "已删")
    assert client.delete(f"/api/logs/{gone['id']}").status_code == 204
    return {"gloves": gloves, "hats": hats, "fid": field["id"],
            "g1": g1, "g2": g2, "h1": h1, "gone": gone}


@pytest.fixture()
def visitor():
    # 新 TestClient 没有任何 Cookie；不用 with，不重复触发 startup
    return TestClient(app)


def _share(client, category_id=None):
    resp = client.post("/api/shares", json={"category_id": category_id})
    assert resp.status_code == 201, resp.text
    return f"/api/share/{resp.json()['token']}"


def _fname(log):
    return log["images"][0]["filename"]


# ------------------------------------------------------------------ 账号级

def test_account_share_readable_without_login(client, data, visitor):
    base = _share(client)
    info = visitor.get(f"{base}/info").json()
    assert info == {"scope": "account", "category_id": None, "category_name": "", "owner": "babelingz"}

    assert [c["name"] for c in visitor.get(f"{base}/categories").json()] == ["手套", "帽子"]
    logs = visitor.get(f"{base}/logs").json()
    assert logs["total"] == 3
    assert {l["id"] for l in logs["items"]} == {data["g1"]["id"], data["g2"]["id"], data["h1"]["id"]}

    by_cat = visitor.get(f"{base}/logs", params={"category_id": data["hats"]}).json()
    assert [l["id"] for l in by_cat["items"]] == [data["h1"]["id"]]
    assert visitor.get(f"{base}/logs", params={"search": "蓝"}).json()["total"] == 1

    assert visitor.get(f"{base}/logs/{data['h1']['id']}").json()["description"] == "红帽子"
    assert len(visitor.get(f"{base}/categories/{data['gloves']}/fields").json()) == 1
    assert visitor.get(f"{base}/files/{_fname(data['h1'])}").status_code == 200
    assert visitor.get(f"{base}/files/thumbs/{_fname(data['h1'])}").status_code == 200


def test_deleted_log_hidden(client, data, visitor):
    base = _share(client)
    assert visitor.get(f"{base}/logs/{data['gone']['id']}").status_code == 404
    assert visitor.get(f"{base}/files/{_fname(data['gone'])}").status_code == 404
    assert visitor.get(f"{base}/files/thumbs/{_fname(data['gone'])}").status_code == 404


# ------------------------------------------------------------------ 分类级

def test_category_share_confined(client, data, visitor):
    base = _share(client, data["gloves"])
    info = visitor.get(f"{base}/info").json()
    assert info == {"scope": "category", "category_id": data["gloves"],
                    "category_name": "手套", "owner": "babelingz"}

    assert [c["name"] for c in visitor.get(f"{base}/categories").json()] == ["手套"]
    assert visitor.get(f"{base}/logs").json()["total"] == 2
    # 显式要别的分类：与范围 AND，结果为空
    assert visitor.get(f"{base}/logs", params={"category_id": data["hats"]}).json()["total"] == 0

    hat = data["h1"]
    assert visitor.get(f"{base}/logs/{hat['id']}").status_code == 404
    assert visitor.get(f"{base}/files/{_fname(hat)}").status_code == 404
    assert visitor.get(f"{base}/files/thumbs/{_fname(hat)}").status_code == 404
    assert visitor.get(f"{base}/categories/{data['hats']}/fields").status_code == 404
    assert visitor.get(f"{base}/categories/{data['gloves']}/fields").status_code == 200


def test_info_reflects_category_rename(client, data, visitor):
    base = _share(client, data["gloves"])
    client.put(f"/api/categories/{data['gloves']}", json={"name": "冬季手套"})
    assert visitor.get(f"{base}/info").json()["category_name"] == "冬季手套"


# ------------------------------------------------------------------ 失效

def _all_gets(visitor, base, data):
    f = _fname(data["g1"])
    return [
        visitor.get(f"{base}/info"),
        visitor.get(f"{base}/categories"),
        visitor.get(f"{base}/categories/{data['gloves']}/fields"),
        visitor.get(f"{base}/logs"),
        visitor.get(f"{base}/logs/{data['g1']['id']}"),
        visitor.get(f"{base}/files/{f}"),
        visitor.get(f"{base}/files/thumbs/{f}"),
    ]


def _assert_all_404(responses):
    for r in responses:
        assert r.status_code == 404, (r.request.url, r.status_code, r.text)
        assert r.json()["detail"] == "分享链接不存在或已失效"


def test_unknown_token_404(data, visitor):
    _assert_all_404(_all_gets(visitor, "/api/share/nope", data))
    _assert_all_404(_all_gets(visitor, "/api/share/" + "x" * 300, data))


def test_revoked_404(client, data, visitor):
    base = _share(client)
    client.delete(f"/api/shares/{base.rsplit('/', 1)[1]}")
    _assert_all_404(_all_gets(visitor, base, data))


def test_disabled_then_reenabled_account(client, data, visitor):
    base = _share(client)
    conn = accounts.connect()
    accounts.set_active(conn, 1, False)
    _assert_all_404(_all_gets(visitor, base, data))
    accounts.set_active(conn, 1, True)
    conn.close()
    assert visitor.get(f"{base}/logs").json()["total"] == 3


def test_category_gone_404(client, visitor):
    cid = client.post("/api/categories", json={"name": "空"}).json()["id"]
    base = _share(client, cid)
    # 删分类本应连分享一起删；这里绕开它，模拟漏删的旧数据
    token = base.rsplit("/", 1)[1]
    conn = accounts.connect()
    conn.execute("DELETE FROM shares WHERE token = ?", (token,))
    conn.execute("INSERT INTO shares (token, user_id, category_id) VALUES (?, 1, ?)", (token, cid + 50))
    conn.commit()
    conn.close()
    assert visitor.get(f"{base}/info").status_code == 404
    assert visitor.get(f"{base}/logs").status_code == 404


# ------------------------------------------------------------------ 越权与边界

def test_other_account_token_cannot_reach_same_ids(client, data, make_user, visitor):
    bob = make_user("bob")
    cid = bob.post("/api/categories", json={"name": "bob 的"}).json()["id"]
    base = _share(bob)
    # bob 库里没有这些 id 的日志和文件
    assert visitor.get(f"{base}/logs").json()["total"] == 0
    assert visitor.get(f"{base}/logs/{data['g1']['id']}").status_code == 404
    assert visitor.get(f"{base}/files/{_fname(data['g1'])}").status_code == 404
    assert cid == data["gloves"]  # 两个账号的分类 id 撞号，确认隔离不靠 id


def test_other_account_cookie_does_not_matter(client, data, make_user):
    base = _share(client, data["gloves"])
    bob = make_user("bob")
    logs = bob.get(f"{base}/logs").json()
    assert {l["id"] for l in logs["items"]} == {data["g1"]["id"], data["g2"]["id"]}
    # 带着别的账号名的请求头也不影响（分享接口不认会话）
    resp = bob.get(f"{base}/logs", headers={"X-PicLog-User": "nobody"})
    assert resp.status_code == 200


def test_file_path_traversal_404(client, data, visitor):
    base = _share(client)
    for name in ("..%2F..%2Fdata%2Fusers%2F1%2Fpiclog.db", "..%2Fpiclog.db", "%2E%2E"):
        assert visitor.get(f"{base}/files/{name}").status_code == 404
        assert visitor.get(f"{base}/files/thumbs/{name}").status_code == 404


def test_logs_page_and_size_bounds(client, data, visitor):
    base = _share(client)
    assert visitor.get(f"{base}/logs", params={"size": 101}).status_code == 422
    assert visitor.get(f"{base}/logs", params={"size": 0}).status_code == 422
    assert visitor.get(f"{base}/logs", params={"page": 0}).status_code == 422
    assert visitor.get(f"{base}/logs", params={"size": 100}).status_code == 200


def test_no_write_methods(client, data, visitor):
    base = _share(client)
    lid, iid = data["g1"]["id"], data["g1"]["images"][0]["id"]
    attempts = [
        visitor.post(f"{base}/logs", data={"category_id": data["gloves"]}),
        visitor.put(f"{base}/logs/{lid}", json={"description": "hacked"}),
        visitor.patch(f"{base}/logs/{lid}/status", json={"status": "completed"}),
        visitor.delete(f"{base}/logs/{lid}"),
        visitor.post(f"{base}/logs/{lid}/images", files=[("files", ("x.png", b"x", "image/png"))]),
        visitor.delete(f"{base}/images/{iid}"),
        visitor.post(f"{base}/categories", json={"name": "x"}),
        visitor.delete(f"{base}/categories/{data['gloves']}"),
    ]
    for r in attempts:
        assert r.status_code in (404, 405), (r.request.method, r.request.url, r.status_code)
    log = client.get(f"/api/logs/{lid}").json()
    assert log["description"] == "红手套" and len(log["images"]) == 1
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_share_access.py -q`
Expected: FAIL（分享接口 404 且 detail 不对、或 `info` 断言失败）

- [ ] **Step 3: 实现 `share_scope`**

`backend/deps.py` 顶部 import 改为：

```python
import logging
import os
import sqlite3
from typing import NamedTuple, Optional
from urllib.parse import unquote
```

末尾追加：

```python
# ------------------------------------------------------------------ 只读分享

SHARE_NOT_FOUND = "分享链接不存在或已失效"


class ShareScope(NamedTuple):
    user_id: int
    username: str
    category_id: Optional[int]   # None = 整个账号
    category_name: str
    db: sqlite3.Connection
    upload_dir: str


def share_scope(token: str):
    """访客侧依赖：token → 账号库连接 + 范围。不读 Cookie，登录与否不影响结果。

    所有失败一律同一个 404，不让访客分辨「不存在」「已撤销」「账号停用」。
    """
    conn = accounts.connect()
    try:
        share = accounts.resolve_share(conn, token)
    finally:
        conn.close()
    if share is None:
        raise HTTPException(404, SHARE_NOT_FOUND)
    path = storage.user_db_path(share["user_id"])
    if not os.path.isfile(path):
        log.error("分享 %s… 指向的库不存在：%s", token[:6], path)
        raise HTTPException(404, SHARE_NOT_FOUND)
    db = database.connect(path)
    try:
        category_name = ""
        if share["category_id"] is not None:
            row = db.execute(
                "SELECT name FROM categories WHERE id = ?", (share["category_id"],)
            ).fetchone()
            if row is None:
                raise HTTPException(404, SHARE_NOT_FOUND)
            category_name = row["name"]
        yield ShareScope(
            user_id=share["user_id"],
            username=share["username"],
            category_id=share["category_id"],
            category_name=category_name,
            db=db,
            upload_dir=storage.user_upload_dir(share["user_id"]),
        )
    finally:
        db.close()
```

- [ ] **Step 4: 实现路由**

`backend/routers/public_share.py`：

```python
"""访客侧：凭分享 token 只读浏览，无需登录。

这里只有读接口和以图搜图，写接口在分享路径下根本不存在。
范围限制收口在 scope_clause：本文件每条读日志 / 图片的 SQL 都必须拼上它，
分类级分享才不会退化成整个账号。
"""
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

import thumbnail
from deps import ShareScope, share_scope
from models import CategoryFieldOut, CategoryOut, LogListOut, LogOut, ShareInfoOut
from routers.fields import FIELD_COLUMNS, _field_row_to_dict
from routers.files import CACHE_HEADERS
from routers.logs import LOG_COLUMNS, _build_log, query_logs

router = APIRouter(prefix="/api/share/{token}", tags=["share"])


def scope_clause(scope: ShareScope) -> tuple[list[str], list]:
    """范围条件（表别名 l）。删除过滤由 query_logs 自带，这里也加上，便于单独使用。"""
    where, params = ["l.deleted_at IS NULL"], []
    if scope.category_id is not None:
        where.append("l.category_id = ?")
        params.append(scope.category_id)
    return where, params


@router.get("/info", response_model=ShareInfoOut)
def info(scope: ShareScope = Depends(share_scope)):
    return {
        "scope": "account" if scope.category_id is None else "category",
        "category_id": scope.category_id,
        "category_name": scope.category_name,
        "owner": scope.username,
    }


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(scope: ShareScope = Depends(share_scope)):
    sql = "SELECT id, name, sort_order, created_at FROM categories"
    params: list = []
    if scope.category_id is not None:
        sql += " WHERE id = ?"
        params.append(scope.category_id)
    rows = scope.db.execute(sql + " ORDER BY sort_order, id", params).fetchall()
    return [dict(r) for r in rows]


@router.get("/categories/{category_id}/fields", response_model=list[CategoryFieldOut])
def list_fields(category_id: int, scope: ShareScope = Depends(share_scope)):
    if scope.category_id is not None and category_id != scope.category_id:
        raise HTTPException(404, "Category not found")
    rows = scope.db.execute(
        f"SELECT {FIELD_COLUMNS} FROM category_fields "
        "WHERE category_id = ? ORDER BY sort_order, id",
        (category_id,),
    ).fetchall()
    return [_field_row_to_dict(scope.db, r) for r in rows]


@router.get("/logs", response_model=LogListOut)
def list_logs(
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    status: Optional[str] = None,
    fv: list[str] = Query(default=[]),
    sort: Optional[str] = None,
    # 匿名接口：不允许一次拉全库，也不允许负 offset
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    scope: ShareScope = Depends(share_scope),
):
    where, params = scope_clause(scope)
    return query_logs(
        scope.db, scope_where=where, scope_params=params,
        search=search, category_id=category_id, status=status,
        fv=fv, sort=sort, page=page, size=size,
    )


@router.get("/logs/{log_id}", response_model=LogOut)
def get_log(log_id: int, scope: ShareScope = Depends(share_scope)):
    where, params = scope_clause(scope)
    row = scope.db.execute(
        f"SELECT {LOG_COLUMNS} FROM logs l WHERE l.id = ? AND {' AND '.join(where)}",
        [log_id, *params],
    ).fetchone()
    if not row:
        raise HTTPException(404, "Log not found")
    return _build_log(scope.db, row)


def _serve(scope: ShareScope, directory: str, filename: str) -> FileResponse:
    # 比主人侧更严：除了登记在 images 表，所属日志还得在分享范围内且未删除
    where, params = scope_clause(scope)
    known = scope.db.execute(
        "SELECT 1 FROM images i JOIN logs l ON l.id = i.log_id "
        f"WHERE i.filename = ? AND {' AND '.join(where)}",
        [filename, *params],
    ).fetchone()
    path = os.path.join(directory, filename)
    if not known or os.path.basename(filename) != filename or not os.path.isfile(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path, headers=CACHE_HEADERS)


@router.get("/files/thumbs/{filename}")
def get_thumbnail(filename: str, scope: ShareScope = Depends(share_scope)):
    return _serve(scope, thumbnail.thumb_dir(scope.upload_dir), filename)


@router.get("/files/{filename}")
def get_original(filename: str, scope: ShareScope = Depends(share_scope)):
    return _serve(scope, scope.upload_dir, filename)
```

`backend/main.py`：

```python
from routers import auth, categories, logs, images, fields, search, files, shares, public_share
...
    app.include_router(shares.router)
    app.include_router(public_share.router)
```

- [ ] **Step 5: 运行，确认通过**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 全部通过。若 `test_file_path_traversal_404` 中某个名字返回 200 —— 停下排查，绝不能放宽断言。

- [ ] **Step 6: 提交**

```bash
git add backend/deps.py backend/routers/public_share.py backend/main.py backend/tests/test_share_access.py
git commit -m "Add read-only public share endpoints scoped by token"
```

---

### Task 5: 访客以图搜图与限流

**Files:**
- Modify: `backend/ratelimit.py`
- Modify: `backend/routers/public_share.py`
- Test: `backend/tests/test_ratelimit.py`（新）、`backend/tests/test_share_access.py`（追加）

**Interfaces:**
- Consumes: `run_image_search`（Task 3）、`share_scope`（Task 4）、`deps.client_ip`
- Produces: `ratelimit.hit(key: tuple, limit: int, window_seconds: float) -> bool`；`POST /api/share/{token}/search/image`

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_ratelimit.py`：

```python
import ratelimit


def test_hit_sliding_window(monkeypatch):
    ratelimit.reset()
    now = [1000.0]
    monkeypatch.setattr(ratelimit, "_clock", lambda: now[0])
    key = ("t", "1.2.3.4")
    assert all(ratelimit.hit(key, 3, 60) for _ in range(3))
    assert ratelimit.hit(key, 3, 60) is False
    # 别的 key 不受影响
    assert ratelimit.hit(("t", "5.6.7.8"), 3, 60) is True
    now[0] += 60.01
    assert ratelimit.hit(key, 3, 60) is True


def test_reset_clears_hits(monkeypatch):
    key = ("t", "x")
    for _ in range(2):
        ratelimit.hit(key, 2, 60)
    ratelimit.reset()
    assert ratelimit.hit(key, 2, 60) is True
```

追加到 `backend/tests/test_share_access.py`：

```python
# ------------------------------------------------------------------ 以图搜图

def _search(c, base, color=RED):
    return c.post(f"{base}/search/image",
                  files={"file": ("q.png", solid_image_bytes(color), "image/png")})


def test_image_search_confined_to_category(client, data, visitor, fake_embedder):
    assert indexer.process_pending() == 3   # 已删除那条不建索引
    base = _share(client, data["gloves"])
    resp = _search(visitor, base)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = [it["log"]["id"] for it in body["items"]]
    assert ids == [data["g1"]["id"]]          # 红帽子在别的分类，不出现
    assert body["pending"] == 0
    assert body["indexed"] == 2


def test_image_search_account_scope(client, data, visitor, fake_embedder):
    indexer.process_pending()
    base = _share(client)
    ids = {it["log"]["id"] for it in _search(visitor, base).json()["items"]}
    assert ids == {data["g1"]["id"], data["h1"]["id"]}


def test_image_search_rate_limited(client, data, visitor, fake_embedder):
    base = _share(client)
    for _ in range(10):
        assert _search(visitor, base).status_code == 200
    resp = _search(visitor, base)
    assert resp.status_code == 429
    assert resp.json()["detail"] == "搜索太频繁，请稍后再试"


def test_image_search_bad_token_404(visitor):
    assert _search(visitor, "/api/share/nope").status_code == 404
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_ratelimit.py tests/test_share_access.py -q -k "hit or reset or image_search"`
Expected: FAIL（`ratelimit.hit` 不存在；`/search/image` 405）

- [ ] **Step 3: 实现**

`backend/ratelimit.py`：顶部 import 加 `from collections import deque`；模块文档字符串末尾追加一行
`另有滑动窗口计数 hit()：给无需登录、又耗算力的接口（分享页以图搜图）限频。`；`_state` 之后加：

```python
# key -> 窗口内各次请求的时刻
_hits: dict[tuple, deque] = {}


def hit(key: tuple, limit: int, window_seconds: float) -> bool:
    """记一次请求；窗口内已达 limit 次则不记并返回 False。"""
    with _lock:
        now = _clock()
        q = _hits.setdefault(key, deque())
        while q and q[0] <= now - window_seconds:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True
```

`reset()` 改为同时清 `_hits`：

```python
def reset():
    with _lock:
        _state.clear()
        _hits.clear()
```

`backend/routers/public_share.py`：import 补充

```python
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

import ratelimit
from deps import ShareScope, client_ip, share_scope
from image_search import MIN_SCORE
from models import CategoryFieldOut, CategoryOut, ImageSearchOut, LogListOut, LogOut, ShareInfoOut
from routers.search import run_image_search
```

文件末尾追加：

```python
# 推理要几秒 CPU，又不需要登录：按 IP 限频
SEARCH_LIMIT = 10
SEARCH_WINDOW_SECONDS = 60


# 同步函数：FastAPI 放到线程池里跑，推理不卡事件循环
@router.post("/search/image", response_model=ImageSearchOut)
def search_by_image(
    request: Request,
    file: UploadFile = File(...),
    limit: int = Query(20, ge=1, le=50),
    scope: ShareScope = Depends(share_scope),
):
    if not ratelimit.hit(("share_search", client_ip(request)), SEARCH_LIMIT, SEARCH_WINDOW_SECONDS):
        raise HTTPException(429, "搜索太频繁，请稍后再试")
    items, indexed = run_image_search(scope.db, file, limit, MIN_SCORE, scope.category_id)
    # 未建索引数对访客没有意义
    return {"items": items, "indexed": indexed, "pending": 0}
```

- [ ] **Step 4: 运行，确认通过**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add backend/ratelimit.py backend/routers/public_share.py backend/tests/test_ratelimit.py backend/tests/test_share_access.py
git commit -m "Add rate-limited image search to public shares"
```

---

### Task 6: 前端数据源抽象（主人侧行为不变）

纯重构：组件改为从 `useSource()` 取数据、路由名、图片地址、以图搜图状态。不 provide 时得到 `ownerSource`，行为与现在完全一致。

**Files:**
- Modify: `frontend/src/thumbs.js`、`frontend/src/imageSearch.js`、`frontend/src/api.js`
- Create: `frontend/src/source.js`
- Modify: `frontend/src/components/LogCard.vue`、`frontend/src/components/CameraSearchButton.vue`
- Modify: `frontend/src/views/LogList.vue`、`frontend/src/views/LogDetail.vue`、`frontend/src/views/ImageSearch.vue`

**Interfaces:**
- Produces（Task 7 的 `createShareSource` 必须返回同形对象）：

```js
// 数据源
{
  readonly: boolean,
  params: object,                 // 路由参数，跳转时展开进 params（主人侧 {}，分享侧 { token }）
  categoryId: number | null,      // 非空 = 锁定在这个分类（分类级分享）
  routes: { list, detail, imageSearch, imageSearchDetail },   // 路由名
  getCategories(), getCategoryFields(cid), getLogs(params), getLog(id),
  thumbUrl(filename), fileUrl(filename),
  imageSearch: { state, searchByPhoto(file), retry() },        // createImageSearch 的返回值
}
```

  - `thumbs.js`：`thumbUrl(filename, base = '/api/files')`、`fileUrl(filename, base = '/api/files')`
  - `imageSearch.js`：`createImageSearch(searchFn) -> { state, searchByPhoto, retry }`；保留 `SCORE_LEVELS`、`scoreLabel`；**删除**模块级 `imageSearch` / `searchByPhoto` / `retry` 导出
  - `api.js`：导出 `formatDetail(detail)`、`toQuery(params) -> URLSearchParams`
  - `source.js`：`ownerSource`、`useSource()`

- [ ] **Step 1: `thumbs.js`**

```js
// 缩略图重新生成过（文件名不变）时加 1：服务器没发缓存头，浏览器会按文件的
// 旧修改时间把旧图缓存好几天，换个地址才能让所有人立刻看到新图。
// 2 = 按 EXIF 摆正后重建（后端 thumbnail.ORIENTED_MARKER）
const THUMB_VERSION = 2

// base：主人侧 /api/files，分享页 /api/share/<token>/files
export function thumbUrl(filename, base = '/api/files') {
  return `${base}/thumbs/${encodeURIComponent(filename)}?v=${THUMB_VERSION}`
}

export function fileUrl(filename, base = '/api/files') {
  return `${base}/${encodeURIComponent(filename)}`
}
```

- [ ] **Step 2: `imageSearch.js` 改为工厂**

```js
// 以图搜图的状态放在组件之外：拍照入口在列表页等其他页面，拍完再跳到结果页；
// 结果页被移走（比如刷新以外的重新挂载）时结果也还在，不用重新识别。
// 每个数据源一份（主人侧一份、每个分享页一份），互不串结果
import { reactive } from 'vue'
import { shrinkForSearch } from './imageCompress.js'

export function createImageSearch(searchFn) {
  const state = reactive({
    status: 'idle', // idle | loading | done | error
    previewUrl: '',
    items: [],
    indexed: 0,
    pending: 0,
    error: '',
    errorStatus: 0,
  })

  let lastFile = null
  // 连续拍了两张时，只采用最后一次请求的结果
  let latest = 0

  async function searchByPhoto(file) {
    lastFile = file
    const token = ++latest
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl)
    Object.assign(state, {
      status: 'loading',
      previewUrl: URL.createObjectURL(file),
      items: [],
      error: '',
      errorStatus: 0,
    })
    try {
      const small = await shrinkForSearch(file)
      const data = await searchFn(small)
      if (token !== latest) return
      Object.assign(state, {
        status: 'done',
        items: data.items,
        indexed: data.indexed,
        pending: data.pending,
      })
    } catch (e) {
      if (token !== latest) return
      Object.assign(state, { status: 'error', error: e.message, errorStatus: e.status || 0 })
    }
  }

  function retry() {
    if (lastFile) searchByPhoto(lastFile)
  }

  return { state, searchByPhoto, retry }
}

// 相似度档位。初值，需用 scripts/eval-search.py 在真实照片上评测后调整
export const SCORE_LEVELS = [
  { min: 0.75, text: '很可能是同一件', cls: 'bg-emerald-500 text-white' },
  { min: 0.5, text: '相似', cls: 'bg-primary-600 text-white' },
  { min: -Infinity, text: '有点像', cls: 'bg-black/50 text-white' },
]

export function scoreLabel(score) {
  return SCORE_LEVELS.find((level) => score >= level.min)
}
```

- [ ] **Step 3: `api.js` 导出两个工具函数**

把 `function formatDetail(detail)` 改为 `export function formatDetail(detail)`。在 `toCardLog` 之前加：

```js
// 数组参数展开成重复的 key（fv=1:2&fv=1:3），空值不发
export function toQuery(params = {}) {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '') continue
    if (Array.isArray(v)) {
      for (const item of v) q.append(k, item)
    } else {
      q.set(k, v)
    }
  }
  return q
}
```

`getLogs` 改为 `getLogs: (params = {}) => request(\`/api/logs?${toQuery(params)}\`),`

- [ ] **Step 4: 新建 `source.js`**

```js
// 「数据源」：列表、详情、以图搜图这几个页面从这里取数据和路由名，而不是直接调 api。
// 主人侧用 ownerSource；分享页（ShareLayout）provide 一个只读的，组件原样复用
import { inject } from 'vue'
import { api } from './api.js'
import { createImageSearch } from './imageSearch.js'
import { fileUrl, thumbUrl } from './thumbs.js'

export const ownerSource = {
  readonly: false,
  params: {},
  categoryId: null,
  routes: {
    list: 'LogList',
    detail: 'LogDetail',
    imageSearch: 'ImageSearch',
    imageSearchDetail: 'ImageSearchDetail',
  },
  getCategories: () => api.getCategories(),
  getCategoryFields: (cid) => api.getCategoryFields(cid),
  getLogs: (params) => api.getLogs(params),
  getLog: (id) => api.getLog(id),
  thumbUrl: (filename) => thumbUrl(filename),
  fileUrl: (filename) => fileUrl(filename),
  imageSearch: createImageSearch((file) => api.searchByImage(file)),
}

export function useSource() {
  return inject('source', ownerSource)
}
```

- [ ] **Step 5: `LogCard.vue`**

模板里 `:to` 改为：

```vue
    :to="{ name: detailRoute || source.routes.detail, params: { ...source.params, id: log.id } }"
```

`:src="thumbUrl(cover.filename)"` 改为 `:src="source.thumbUrl(cover.filename)"`。

script：删除 `import { thumbUrl } from '../thumbs.js'`，加 `import { useSource } from '../source.js'`；
`detailRoute` 的 default 改为 `''`，注释改为「点开时用哪个详情路由；不传就用数据源的列表详情」；
`const cover = …` 之前加 `const source = useSource()`。

- [ ] **Step 6: `CameraSearchButton.vue`**

script 中删除 `import { searchByPhoto } from '../imageSearch.js'`，加 `import { useSource } from '../source.js'`，并：

```js
const source = useSource()

function onPick(files) {
  source.imageSearch.searchByPhoto(files[0])
  const name = source.routes.imageSearch
  if (route.name !== name) router.push({ name, params: source.params })
}
```

- [ ] **Step 7: `ImageSearch.vue`**

模板：所有 `imageSearch.` 不变（下面让 `imageSearch` 指向 `source.imageSearch.state`）；`detail-route="ImageSearchDetail"` 改为
`:detail-route="source.routes.imageSearchDetail"`。

script 改为：

```js
import { computed, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { toCardLog } from '../api.js'
import DetailSheet from '../components/DetailSheet.vue'
import PageHeader from '../components/PageHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import LogCard from '../components/LogCard.vue'
import CameraSearchButton from '../components/CameraSearchButton.vue'
import { scoreLabel } from '../imageSearch.js'
import { useSource } from '../source.js'

const source = useSource()
const imageSearch = source.imageSearch.state
const retry = () => source.imageSearch.retry()

const errorMessage = computed(() =>
  imageSearch.errorStatus === 503
    ? '以图搜图未启用，请联系管理员放置模型文件'
    : imageSearch.error || '搜索失败',
)

// 详情卡片关掉后只刷新那一条（改了状态/内容、或删掉了），不重新识别
async function refreshHit(id) {
  try {
    const log = toCardLog(await source.getLog(id))
    const hit = imageSearch.items.find((h) => h.log.id === log.id)
    if (hit) hit.log = log
  } catch (e) {
    if (e.status !== 404) return
    imageSearch.items = imageSearch.items.filter((h) => String(h.log.id) !== String(id))
  }
}

const removeAfterEach = useRouter().afterEach((to, from, failure) => {
  if (!failure && from.name === source.routes.imageSearchDetail && to.name === source.routes.imageSearch) {
    refreshHit(from.params.id)
  }
})
onBeforeUnmount(removeAfterEach)
```

- [ ] **Step 8: `LogDetail.vue`（本任务只换数据源，只读在 Task 7 做）**

- `import { api } from '../api.js'` 保留（写操作仍走主人 api）；删除 `import { thumbUrl } from '../thumbs.js'`，加 `import { useSource } from '../source.js'`，`const route = useRoute()` 前加 `const source = useSource()`
- `loadLog` 中 `api.getLog(...)` → `source.getLog(...)`
- 模板 `:src="thumbUrl(img.filename)"` → `:src="source.thumbUrl(img.filename)"`
- 预览大图 `` :src="`/api/files/${encodeURIComponent(previewImg.filename)}`" `` → `:src="source.fileUrl(previewImg.filename)"`
- `close()` 改为按路由名回退（`matched[...].path` 在分享页是带 `:token` 的模式串，不能直接用）：

```js
// 从列表/搜图结果点进来的就退回去（Android 返回键、微信返回手势走的也是这条路），
// 直接打开链接进来的没有上一页，换成卡片所在的宿主页面
function close() {
  if (window.history.state?.back) return router.back()
  const host = route.matched[route.matched.length - 2]
  const { id, ...params } = route.params
  if (host?.name) router.replace({ name: host.name, params })
  else router.replace('/')
}
```

- [ ] **Step 9: `LogList.vue`**

script：
- `import { api, toCardLog } from '../api.js'` → `import { toCardLog } from '../api.js'`，加 `import { useSource } from '../source.js'`
- 在 `const logs = ref([])` 之前加 `const source = useSource()`
- `const filterCategory = ref('')` → `const filterCategory = ref(source.categoryId ?? '')`
- 把 watcher 中加载字段的部分抽出：

```js
async function loadFields(cid) {
  try {
    activeFields.value = cid ? await source.getCategoryFields(cid) : []
  } catch (e) {
    alert(e.message)
    activeFields.value = []
  }
}

watch(filterCategory, async (cid) => {
  // 换分类就把该分类专属的筛选条件全部重置，并由 watcher 统一负责重新加载，
  // 避免点击分类的 handler 在 filterCategory 更新之后、watcher 刷新 state 之前
  // 就同步跑完 load()，带着上一个分类的筛选/排序状态发请求。
  selectedOptions.value = {}
  optionQueries.value = {}
  sortValue.value = ''
  await loadFields(cid)
  load()
})
```

- `fetchPage` 中 `api.getLogs` → `source.getLogs`
- `refreshItem` 中 `api.getLog` → `source.getLog`
- `afterEach` 中 `from.name === 'LogDetail' && to.name === 'LogList'` → `from.name === source.routes.detail && to.name === source.routes.list`（`LogCreate` 那行不动）
- `onActivated` 与 `onMounted` 中 `api.getCategories()` → `source.getCategories()`
- `onMounted` 中 `load()` 之前加：

```js
  // 分类级分享一开始就锁定在该分类：watcher 不会因初始值触发，字段筛选要手动拉
  if (filterCategory.value) await loadFields(filterCategory.value)
```

- [ ] **Step 10: 构建**

Run: `cd frontend && npm run build`
Expected: 成功，无报错。再用 `grep -rn "from '../thumbs.js'\|imageSearch.js'" frontend/src` 确认只剩 `source.js`、`ImageSearch.vue`（`scoreLabel`）在引用。

- [ ] **Step 11: 手动回归（主人侧）**

后端 `cd backend && .venv/bin/uvicorn main:app --port 8080`（环境变量见 `.env.example`；或用 `scripts/setup-dev.sh` 已配好的方式），前端 `cd frontend && npm run dev`。登录后逐项确认：列表加载与无限滚动、分类筛选后出现字段筛选与排序、打开详情卡片 / Esc 关闭 / 直接打开 `/logs/<id>` 再关闭回到列表、详情里改状态后关闭列表那条随之更新、拍照搜索跳到结果页并能打开结果详情、缩略图与大图预览正常。

- [ ] **Step 12: 提交**

```bash
git add frontend/src
git commit -m "Route list, detail and image search through an injectable data source"
```

---

### Task 7: 分享页（访客侧前端）

**Files:**
- Create: `frontend/src/shareApi.js`、`frontend/src/views/ShareLayout.vue`
- Modify: `frontend/src/router.js`
- Modify: `frontend/src/views/LogList.vue`、`frontend/src/views/LogDetail.vue`（只读）

**Interfaces:**
- Consumes: Task 6 的数据源形状、`createImageSearch`、`thumbUrl/fileUrl(filename, base)`、`formatDetail`、`toQuery`；Task 4/5 的 HTTP 接口
- Produces: `createShareSource(token)`；路由名 `ShareList`、`ShareDetail`、`ShareImageSearch`、`ShareImageSearchDetail`

- [ ] **Step 1: `shareApi.js`**

```js
// 分享页的数据源：只读，请求不带登录信息。
// 不走 api.js 的 request：那边 401 会跳登录页，还会带上「我是谁」的请求头
import { formatDetail, toQuery } from './api.js'
import { createImageSearch } from './imageSearch.js'
import { fileUrl, thumbUrl } from './thumbs.js'

async function shareRequest(url, options) {
  const res = await fetch(url, options)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw Object.assign(new Error(formatDetail(err.detail) || '请求失败'), { status: res.status })
  }
  return res.json()
}

export function createShareSource(token) {
  const base = `/api/share/${encodeURIComponent(token)}`
  const filesBase = `${base}/files`

  return {
    readonly: true,
    params: { token },
    // 由 ShareLayout 在拿到 /info 后填上
    categoryId: null,
    routes: {
      list: 'ShareList',
      detail: 'ShareDetail',
      imageSearch: 'ShareImageSearch',
      imageSearchDetail: 'ShareImageSearchDetail',
    },
    getInfo: () => shareRequest(`${base}/info`),
    getCategories: () => shareRequest(`${base}/categories`),
    getCategoryFields: (cid) => shareRequest(`${base}/categories/${cid}/fields`),
    getLogs: (params) => shareRequest(`${base}/logs?${toQuery(params)}`),
    getLog: (id) => shareRequest(`${base}/logs/${id}`),
    thumbUrl: (filename) => thumbUrl(filename, filesBase),
    fileUrl: (filename) => fileUrl(filename, filesBase),
    imageSearch: createImageSearch((file) => {
      const fd = new FormData()
      fd.append('file', file)
      return shareRequest(`${base}/search/image?limit=20`, { method: 'POST', body: fd })
    }),
  }
}
```

- [ ] **Step 2: `ShareLayout.vue`**

```vue
<template>
  <div>
    <div v-if="state === 'loading'" class="flex items-center justify-center py-24 text-sm text-slate-400">
      加载中...
    </div>

    <EmptyState v-else-if="state === 'invalid'" message="分享链接不存在或已失效" />

    <div v-else-if="state === 'error'" class="py-24 text-center text-sm text-slate-500">
      <p>{{ error }}</p>
      <button @click="init" class="mt-3 font-medium text-primary-600">重试</button>
    </div>

    <template v-else>
      <header class="mb-4">
        <h1 class="text-lg font-bold text-slate-900">{{ title }}</h1>
        <p class="text-xs text-slate-400">只读分享</p>
      </header>
      <!-- 同 App.vue：从详情卡片回来时列表和搜图结果的状态都保留 -->
      <router-view v-slot="{ Component }">
        <keep-alive :include="['LogList', 'ImageSearch']">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, provide, ref } from 'vue'
import { useRoute } from 'vue-router'
import EmptyState from '../components/EmptyState.vue'
import { createShareSource } from '../shareApi.js'

// token 只在进入时读一次：站内没有从一个分享跳到另一个分享的入口
const source = createShareSource(useRoute().params.token)
provide('source', source)

const state = ref('loading') // loading | ready | invalid | error
const error = ref('')
const info = ref(null)

const title = computed(() => {
  if (!info.value) return ''
  const { owner, scope, category_name: name } = info.value
  return scope === 'category' ? `${owner} 分享的「${name}」` : `${owner} 分享的全部内容`
})

async function init() {
  state.value = 'loading'
  try {
    info.value = await source.getInfo()
    // 子页面在 ready 之后才挂载，挂载时读到的就是锁定的分类
    source.categoryId = info.value.category_id
    document.title = `${title.value} - PicLog`
    state.value = 'ready'
  } catch (e) {
    if (e.status === 404) {
      state.value = 'invalid'
    } else {
      error.value = e.message
      state.value = 'error'
    }
  }
}

onMounted(init)
</script>
```

- [ ] **Step 3: 路由**

`frontend/src/router.js`：import 加 `import ShareLayout from './views/ShareLayout.vue'`，`routes` 末尾追加：

```js
  {
    // 只读分享：不需要登录，已登录的人打开看到的也是分享内容
    path: '/s/:token',
    component: ShareLayout,
    meta: { public: true, share: true },
    children: [
      {
        path: '',
        name: 'ShareList',
        component: LogList,
        children: [{ path: 'logs/:id(\\d+)', name: 'ShareDetail', component: LogDetail }],
      },
      {
        path: 'search/image',
        name: 'ShareImageSearch',
        component: ImageSearch,
        children: [{ path: 'logs/:id(\\d+)', name: 'ShareImageSearchDetail', component: LogDetail }],
      },
    ],
  },
```

守卫改为（`share` 判断必须在最前，不发 `/api/auth/me`、不重定向）：

```js
router.beforeEach(async (to) => {
  if (to.meta.share) return true
  const user = await ensureSession()
  if (to.meta.public) return user ? { path: '/' } : true
  if (!user) return { name: 'Login', query: { redirect: to.fullPath } }
  return true
})
```

`scrollBehavior` 不改：`to.matched[0]` 在分享页是 ShareLayout，列表与详情之间切换照样不动滚动条。

- [ ] **Step 4: `LogList.vue` 只读**

- 搜索栏下的分类 pills（「全部」按钮和 `v-for="c in categories"` 两个按钮，以及其后的分隔 `<span class="mx-0.5 w-px …">`）包进 `<template v-if="!source.categoryId">…</template>`，分类级分享只剩状态筛选
- 空状态里的「新建日志」`<router-link>` 加 `v-if="!source.readonly"`

- [ ] **Step 5: `LogDetail.vue` 只读**

- 头部编辑 `<router-link>` 与删除 `<button>` 所在的 `<template v-if="log">` 改为 `<template v-if="log && !source.readonly">`
- 图片区标题右侧的 `<div class="flex items-center gap-2">`（压缩开关、追加上传、PhotoSourceSheet）加 `v-if="!source.readonly"`
- 每张图右上角删除按钮加 `v-if="!source.readonly"`
- 末尾「Add card」按钮加 `v-if="!source.readonly"`
- 状态行的切换按钮（「标记完成 / 标记待处理」）加 `v-if="!source.readonly"`
- 空图片提示保持不变

- [ ] **Step 6: 构建**

Run: `cd frontend && npm run build`
Expected: 成功

- [ ] **Step 7: 手动验证**

后端与前端开发服务器同 Task 6。用 curl 建两个分享（需登录 Cookie，可在浏览器开发者工具里复制 `piclog_session`），或直接等 Task 8 的界面；这里用 curl：

```bash
curl -s -b "piclog_session=<cookie>" -H 'Content-Type: application/json' -d '{}' http://localhost:8080/api/shares
curl -s -b "piclog_session=<cookie>" -H 'Content-Type: application/json' -d '{"category_id": <某分类id>}' http://localhost:8080/api/shares
```

逐项确认：
1. 无痕窗口打开 `http://localhost:5173/s/<账号级token>`：标题「xx 分享的全部内容」；没有顶栏、底栏、新建按钮；分类、状态、字段筛选与排序、文字搜索都可用；详情卡片没有编辑 / 删除 / 改状态 / 上传 / 删图；大图预览正常；拍照搜索跳到 `/s/<token>/search/image` 并能打开结果详情；直接打开 `/s/<token>/logs/<id>` 再关闭回到分享列表
2. 分类级 token：标题含分类名；没有分类 pills；字段筛选一开始就出现；直接打开别的分类日志的地址 `/s/<token>/logs/<id>` → 卡片显示「日志不存在或已删除」
3. 已登录的普通窗口打开分享链接：看到的是分享页而不是被跳回首页；回到 `/` 仍是自己的数据
4. 随便改一个字符的 token：显示「分享链接不存在或已失效」

- [ ] **Step 8: 提交**

```bash
git add frontend/src
git commit -m "Add read-only share pages for visitors"
```

---

### Task 8: 主人侧分享管理界面

**Files:**
- Modify: `frontend/src/api.js`
- Create: `frontend/src/shareLink.js`、`frontend/src/components/ShareLinkField.vue`、`frontend/src/views/Shares.vue`
- Modify: `frontend/src/views/Categories.vue`、`frontend/src/router.js`

**Interfaces:**
- Consumes: Task 2 的 `/api/shares` 接口（`ShareOut`：`token, category_id, category_name, created_at`）
- Produces: `api.getShares()`、`api.createShare(categoryId)`、`api.deleteShare(token)`；`shareUrl(token)`、`copyText(text) -> Promise<boolean>`；路由 `/shares`（name `Shares`）

- [ ] **Step 1: `api.js`**

在 `// Image search` 之前加：

```js
  // Shares
  getShares: () => request('/api/shares'),
  // categoryId 为 null = 分享整个账号
  createShare: (categoryId) => request('/api/shares', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category_id: categoryId }),
  }),
  deleteShare: (token) => request(`/api/shares/${encodeURIComponent(token)}`, { method: 'DELETE' }),
```

- [ ] **Step 2: `shareLink.js`**

```js
export function shareUrl(token) {
  return `${window.location.origin}/s/${token}`
}

// NAS 走 http，非 localhost 下 navigator.clipboard 不可用（只在安全上下文里有），
// 返回 false 时由调用方选中文本让用户手动复制
export async function copyText(text) {
  if (!window.isSecureContext || !navigator.clipboard) return false
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
```

- [ ] **Step 3: `ShareLinkField.vue`**

```vue
<template>
  <div>
    <div class="flex gap-2">
      <input
        ref="input"
        :value="url"
        readonly
        @focus="$event.target.select()"
        class="min-w-0 flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700"
      />
      <button
        type="button"
        @click="copy"
        class="shrink-0 rounded-xl bg-primary-600 px-3 py-2 text-xs font-medium text-white shadow-sm transition-colors hover:bg-primary-700"
      >
        {{ copied ? '已复制' : '复制' }}
      </button>
    </div>
    <p v-if="manual" class="mt-1.5 text-[11px] text-amber-600">已选中链接，请长按或用 Ctrl+C 复制</p>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { copyText, shareUrl } from '../shareLink.js'

const props = defineProps({ token: { type: String, required: true } })

const url = computed(() => shareUrl(props.token))
const input = ref(null)
const copied = ref(false)
const manual = ref(false)

async function copy() {
  if (await copyText(url.value)) {
    copied.value = true
    manual.value = false
    setTimeout(() => { copied.value = false }, 1500)
  } else {
    input.value.focus()
    input.value.select()
    manual.value = true
  }
}
</script>
```

- [ ] **Step 4: `Shares.vue`**

```vue
<template>
  <div>
    <PageHeader title="我的分享" back />

    <p class="mb-4 text-xs text-slate-500">拿到链接的人无需登录即可只读浏览。撤销后链接立即失效。</p>

    <div v-if="loading" class="py-16 text-center text-sm text-slate-400">加载中...</div>
    <EmptyState v-else-if="shares.length === 0" message="还没有分享链接，可在分类管理里创建" />

    <div v-else class="space-y-3">
      <div
        v-for="s in shares"
        :key="s.token"
        class="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm"
      >
        <div class="mb-2 flex items-center justify-between gap-2">
          <div class="min-w-0">
            <p class="truncate text-sm font-medium text-slate-900">{{ scopeLabel(s) }}</p>
            <p class="text-[11px] text-slate-400">创建于 {{ formatDate(s.created_at) }}</p>
          </div>
          <button
            @click="revoke(s)"
            class="shrink-0 rounded-lg px-2.5 py-1 text-xs font-medium text-red-500 transition-colors hover:bg-red-50"
          >
            撤销
          </button>
        </div>
        <ShareLinkField :token="s.token" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'
import PageHeader from '../components/PageHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import ShareLinkField from '../components/ShareLinkField.vue'

const shares = ref([])
const loading = ref(true)

function scopeLabel(s) {
  if (s.category_id === null) return '全部内容'
  return s.category_name ? `分类「${s.category_name}」` : '分类（已删除）'
}

// 后端存的是 UTC、不带时区的 "YYYY-MM-DD HH:MM:SS"
function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt.replace(' ', 'T') + 'Z').toLocaleString('zh-CN')
}

async function load() {
  try {
    shares.value = await api.getShares()
  } catch (e) {
    alert(e.message)
  } finally {
    loading.value = false
  }
}

async function revoke(s) {
  if (!confirm(`撤销「${scopeLabel(s)}」的分享？已发出的链接将无法打开。`)) return
  try {
    await api.deleteShare(s.token)
    shares.value = shares.value.filter((x) => x.token !== s.token)
  } catch (e) {
    alert(e.message)
  }
}

onMounted(load)
</script>
```

- [ ] **Step 5: `Categories.vue`**

模板：
- `<PageHeader title="分类管理" />` 改为：

```vue
    <PageHeader title="分类管理">
      <template #actions>
        <router-link
          to="/shares"
          class="rounded-lg px-2.5 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100"
        >
          我的分享
        </router-link>
        <button
          @click="share(null)"
          class="rounded-lg px-2.5 py-1.5 text-sm font-medium text-primary-600 transition-colors hover:bg-primary-50"
        >
          分享全部
        </button>
      </template>
    </PageHeader>
```

- 显示模式下「字段」链接之前加：

```vue
            <button
              @click="share(c)"
              class="flex h-8 items-center rounded-lg px-2 text-xs font-medium text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            >
              分享
            </button>
```

- 根 `<div>` 的最后（退出登录卡片之后）加弹窗：

```vue
    <!-- 新建的分享链接 -->
    <div
      v-if="created"
      class="fixed inset-0 z-[60] flex items-end justify-center bg-black/40 p-4 sm:items-center"
      @click.self="created = null"
    >
      <div class="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl">
        <h2 class="mb-1 text-base font-bold text-slate-900">已创建分享链接</h2>
        <p class="mb-3 text-xs text-slate-500">
          {{ created.category_id === null ? '全部内容' : `分类「${created.category_name}」` }}，
          拿到链接的人无需登录即可只读浏览。可在「我的分享」里随时撤销。
        </p>
        <ShareLinkField :token="created.token" />
        <div class="mt-4 text-right">
          <button @click="created = null" class="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-500 hover:bg-slate-100">
            关闭
          </button>
        </div>
      </div>
    </div>
```

script：加 `import ShareLinkField from '../components/ShareLinkField.vue'`，以及：

```js
const created = ref(null)

// c 为 null = 分享整个账号
async function share(c) {
  try {
    created.value = await api.createShare(c ? c.id : null)
  } catch (e) {
    alert(e.message)
  }
}
```

- [ ] **Step 6: 路由**

`frontend/src/router.js`：import 加 `import Shares from './views/Shares.vue'`；在 `CategoryFields` 路由之后加
`{ path: '/shares', name: 'Shares', component: Shares },`

- [ ] **Step 7: 构建与手动验证**

Run: `cd frontend && npm run build` → 成功。

手动：分类管理页点某分类「分享」→ 弹窗显示链接，复制可用（localhost 是安全上下文；再用局域网 IP 打开确认复制失败时会选中文本并提示）；「分享全部」同理；「我的分享」列出两条，新的在前，范围与时间正确；撤销后列表移除，无痕窗口打开该链接显示失效；删除一个只有分享、没有日志的空分类后，「我的分享」里对应条目消失。

- [ ] **Step 8: 提交**

```bash
git add frontend/src
git commit -m "Add share link management for owners"
```

---

### Task 9: 收尾验证

- [ ] **Step 1:** `cd backend && .venv/bin/python -m pytest -q` → 全部通过，记下数量
- [ ] **Step 2:** `cd frontend && npm run build` → 成功
- [ ] **Step 3:** 用生产形态跑一遍：`docker compose build` 后按 `.env.example` 启动（或项目现有的本地运行方式），确认 SPA 兜底路由能直接打开 `/s/<token>` 和 `/s/<token>/logs/<id>`（刷新不 404）
- [ ] **Step 4:** 对照 spec「测试」一节逐条核对都有对应测试或手动验证记录
- [ ] **Step 5:** 不 push（pre-push 会部署）；告知用户分支状态，由用户决定何时部署
