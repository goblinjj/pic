# 多用户与管理后台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 PicLog 改成多账号：登录后进入完全独立的数据环境（各自的库、图片、搜图索引），账号只能在隐藏路径下的管理后台创建和管理。

**Architecture:** 新增 `accounts.db` 存账号 / 会话 / 管理员；每个账号一个 `data/users/<id>/piclog.db` 和 `uploads/users/<id>/`。所有路由原本都通过 `Depends(get_db)` 拿连接，把这个依赖换成「按会话找到用户 → 打开该用户的库」，现有 SQL 不改。管理后台是一个不进前端打包的单文件 HTML，挂在环境变量 `ADMIN_PATH` 指定的前缀下。

**Tech Stack:** FastAPI 0.115、SQLite、Python 标准库（`hashlib.scrypt`、`secrets`、`hmac`），Vue 3 + vue-router 4 + Vite，pytest + httpx TestClient。不新增任何依赖。

**Spec:** `docs/superpowers/specs/2026-09-29-multi-user-design.md`

## Global Constraints

- 不新增 Python 或 npm 依赖
- 首个账号用户名：`babelingz`，id 必须为 1；密码只来自环境变量 `INITIAL_USER_PASSWORD`
- 机密（`ADMIN_PATH`、`ADMIN_PASSWORD`、`INITIAL_USER_PASSWORD` 的真实值）绝不写入仓库中的任何文件、测试或提交信息
- 用户名：`^[a-z0-9_]{3,32}$`；密码长度 8–128
- 密码哈希：`scrypt$<n>$<r>$<p>$<salt_hex>$<hash_hex>`，n=2^14, r=8, p=1，16 字节盐，32 字节输出；比较用 `hmac.compare_digest`
- 用户会话 Cookie `piclog_session`：HttpOnly、SameSite=Lax、Path=/、30 天；剩余不足 29 天时续期到 30 天
- 管理员会话 Cookie `piclog_admin`：HttpOnly、SameSite=Strict、Path=`/<ADMIN_PATH>`、12 小时、不续期
- 登录失败统一返回 401 `账号或密码错误`；连续失败 5 次锁 15 分钟，锁定期间返回 429
- 管理后台路由 `include_in_schema=False`，不能出现在 `/openapi.json`
- 代码注释、错误提示用中文，风格与现有代码一致（注释解释「为什么」）
- 每个任务结束时 `cd backend && .venv/bin/pytest tests -q` 全部通过

## Spec 的两处细化（实施时同步改 spec）

1. **文件接口不用文件名正则，改为查库**：旧数据的扩展名来自用户上传的原始文件名（如 `.jpg(1)`），正则会把合法旧图挡成 404。改为「文件名必须等于当前用户库 `images.filename` 中的某一项，且 `basename(name) == name`」，同样杜绝路径穿越，并且额外保证只能读自己登记过的文件。
2. **用户登录限流键为 `(IP, 用户名)`**，管理员登录为 IP：群晖 Docker 默认的 userland-proxy 会让所有客户端看起来来自同一个网关 IP，只按 IP 计数的话，一个人输错 5 次就会锁住所有人。

Task 3 的最后一步负责把这两点写回 spec。

## Review Focus

1. **首次迁移中途断电**：库已移走、图片只移了一半 → 重启后应继续完成，不丢文件、不报冲突（Task 2 `test_resume_after_partial_move`）
2. **源和目标同时存在**（有人手工拷过文件）→ 应拒绝启动并说明哪个文件冲突，而不是覆盖（Task 2 `test_conflict_refuses_to_overwrite`）
3. **停用账号或重置密码后，旧 Cookie 仍在浏览器里** → 下一个请求就应 401，而不是等到过期（Task 4 `test_deactivated_user_session_is_rejected`、`test_password_reset_revokes_sessions`）
4. **管理后台路径通过 `/openapi.json` 或 `/docs` 泄露** → openapi 中不应出现该前缀（Task 6 `test_admin_routes_hidden_from_openapi`）
5. **一个账号输错密码把别人锁在外面**（所有请求同一 IP）→ 其他用户名仍可登录（Task 4 `test_lockout_is_per_username`）

---

## File Structure

新建：

| 文件 | 职责 |
| --- | --- |
| `backend/storage.py` | 目录布局：accounts.db / 每用户库 / 每用户上传目录的路径；新账号开户；旧布局迁移 |
| `backend/accounts.py` | accounts.db 的表结构与全部读写：密码哈希、用户、会话、管理员、meta |
| `backend/bootstrap.py` | 启动时的一次性工作：建账号库、迁移旧数据、建首个账号、写管理员密码、逐用户 init_db 与缩略图补全 |
| `backend/ratelimit.py` | 进程内登录失败计数与锁定 |
| `backend/deps.py` | FastAPI 依赖：`current_user`、`current_user_id`、`get_db`、`get_upload_dir`、会话 Cookie 读写 |
| `backend/routers/auth.py` | `/api/auth/login|logout|me`、`/api/health` |
| `backend/routers/files.py` | `/api/files/{name}`、`/api/files/thumbs/{name}` |
| `backend/admin.py` | 管理后台路由工厂 `build_router(path)` 与 `configured_path()` |
| `backend/admin_page/index.html` | 管理后台单文件页面 |
| `frontend/src/auth.js` | 前端登录状态 |
| `frontend/src/views/Login.vue` | 登录页 |
| `.env.example` | NAS 上 `.env` 的模板（只有键，没有值） |
| 测试 | `test_accounts.py`、`test_storage_migration.py`、`test_auth.py`、`test_files.py`、`test_isolation.py`、`test_admin.py` |

修改：`database.py`（去掉全局 DB_PATH / get_db，`init_db(path)`）、`thumbnail.py`（函数接收上传目录）、`indexer.py`（逐用户扫描）、`routers/*.py`（依赖从 `deps` 导入）、`main.py`（`create_app()`、启动走 bootstrap、移除 `/uploads` 静态挂载）、`tests/conftest.py`、若干现有测试、前端 `api.js`/`router.js`/`App.vue`/`TopBar.vue`/`Categories.vue`/`thumbs.js`/`LogDetail.vue`/`vite.config.js`、`docker-compose.yml`、`.gitignore`、`.dockerignore`、`scripts/deploy.sh`、`scripts/setup-dev.sh`、`scripts/eval-search.py`。

---

### Task 1: 账号库（accounts.py + storage 路径）

**Files:**
- Create: `backend/storage.py`（本任务只放路径函数）
- Create: `backend/accounts.py`
- Test: `backend/tests/test_accounts.py`

**Interfaces:**
- Produces（storage）：`DATA_DIR: str`、`UPLOAD_ROOT: str`（模块属性，函数调用时读取，测试可 monkeypatch）、`accounts_db_path() -> str`、`legacy_db_path() -> str`、`user_dir(uid: int) -> str`、`user_db_path(uid: int) -> str`、`user_upload_dir(uid: int) -> str`
- Produces（accounts）：
  - `hash_password(pw: str) -> str`、`verify_password(pw: str, stored: str) -> bool`
  - `connect() -> sqlite3.Connection`（row_factory=Row，外键开）、`init_schema(conn)`
  - `class UsernameTaken(Exception)`；`create_user(conn, username, password) -> int`（非法输入抛 `ValueError`）
  - `get_user(conn, uid) -> Row | None`、`list_users(conn) -> list[Row]`、`all_user_ids(conn) -> list[int]`、`active_user_ids(conn) -> list[int]`
  - `authenticate(conn, username, password) -> Row | None`（停用账号返回 None）
  - `set_password(conn, uid, password)`、`set_active(conn, uid, active: bool)`（二者都删除该用户全部会话）
  - `create_session(conn, uid) -> str`（明文 token）、`resolve_session(conn, token) -> tuple[Row, bool] | None`（bool=是否续期了）、`delete_session(conn, token)`、`purge_expired_sessions(conn)`
  - `admin_configured(conn) -> bool`、`set_admin_password_if_missing(conn, pw) -> bool`、`verify_admin(conn, pw) -> bool`、`create_admin_session(conn) -> str`、`check_admin_session(conn, token) -> bool`、`delete_admin_session(conn, token)`
  - `get_meta(conn, key) -> str | None`、`set_meta(conn, key, value)`
  - `_now() -> datetime`（UTC，测试 monkeypatch 它来模拟时间流逝）
  - 常量 `SESSION_TTL = timedelta(days=30)`、`SESSION_RENEW_BELOW = timedelta(days=29)`、`ADMIN_SESSION_TTL = timedelta(hours=12)`

- [ ] **Step 1: 写 storage.py 的路径函数**

```python
"""数据目录布局。

    <DATA_DIR>/accounts.db             账号、会话、管理员
    <DATA_DIR>/users/<id>/piclog.db    每个账号自己的业务库
    <UPLOAD_ROOT>/users/<id>/          每个账号自己的原图
    <UPLOAD_ROOT>/users/<id>/thumbs/   以及缩略图

DATA_DIR 沿用旧的 DB_PATH 环境变量所在目录，部署配置不用改。
两个目录都是模块属性、在函数里现取：测试可以 monkeypatch 到临时目录。
"""
import os

DATA_DIR = os.path.dirname(os.environ.get("DB_PATH", "/app/data/piclog.db"))
UPLOAD_ROOT = os.environ.get("UPLOAD_DIR", "/app/uploads")

USER_DB_NAME = "piclog.db"


def accounts_db_path() -> str:
    return os.path.join(DATA_DIR, "accounts.db")


def legacy_db_path() -> str:
    """单用户时代的库：首次升级时整体移给 1 号账号。"""
    return os.path.join(DATA_DIR, USER_DB_NAME)


def user_dir(uid: int) -> str:
    return os.path.join(DATA_DIR, "users", str(uid))


def user_db_path(uid: int) -> str:
    return os.path.join(user_dir(uid), USER_DB_NAME)


def user_upload_dir(uid: int) -> str:
    return os.path.join(UPLOAD_ROOT, "users", str(uid))
```

- [ ] **Step 2: 写失败的测试 `backend/tests/test_accounts.py`**

这些测试只碰 accounts.db，不需要 `client`。用 `tmp_path` 隔离。

```python
from datetime import timedelta

import pytest

import accounts
import storage


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    c = accounts.connect()
    accounts.init_schema(c)
    yield c
    c.close()


@pytest.fixture()
def clock(monkeypatch):
    """可拨动的时钟：clock.advance(timedelta(...))。"""
    class Clock:
        now = accounts._now()

        def advance(self, delta):
            self.now += delta

    c = Clock()
    monkeypatch.setattr(accounts, "_now", lambda: c.now)
    return c


def test_password_hash_roundtrip():
    h = accounts.hash_password("correct horse")
    assert h.startswith("scrypt$16384$8$1$")
    assert accounts.verify_password("correct horse", h)
    assert not accounts.verify_password("wrong horse", h)


def test_same_password_gets_different_salt():
    assert accounts.hash_password("same-pass") != accounts.hash_password("same-pass")


@pytest.mark.parametrize("stored", ["", "plain", "scrypt$1$2", "bcrypt$x$y$z$aa$bb"])
def test_malformed_hash_never_verifies(stored):
    assert not accounts.verify_password("anything", stored)


def test_create_and_authenticate(conn):
    uid = accounts.create_user(conn, "alice", "password-1")
    assert uid == 1
    user = accounts.authenticate(conn, "alice", "password-1")
    assert user["id"] == uid and user["username"] == "alice"
    assert accounts.authenticate(conn, "alice", "wrong-pass") is None
    assert accounts.authenticate(conn, "nobody", "password-1") is None


@pytest.mark.parametrize("username", ["ab", "Alice", "a-b", "a" * 33, "中文名", ""])
def test_invalid_username_rejected(conn, username):
    with pytest.raises(ValueError):
        accounts.create_user(conn, username, "password-1")


@pytest.mark.parametrize("password", ["short", "x" * 129])
def test_invalid_password_rejected(conn, password):
    with pytest.raises(ValueError):
        accounts.create_user(conn, "alice", password)


def test_duplicate_username(conn):
    accounts.create_user(conn, "alice", "password-1")
    with pytest.raises(accounts.UsernameTaken):
        accounts.create_user(conn, "alice", "password-2")


def test_inactive_user_cannot_authenticate(conn):
    uid = accounts.create_user(conn, "alice", "password-1")
    accounts.set_active(conn, uid, False)
    assert accounts.authenticate(conn, "alice", "password-1") is None
    assert accounts.active_user_ids(conn) == []
    assert accounts.all_user_ids(conn) == [uid]


def test_session_resolves_and_logout_deletes(conn):
    uid = accounts.create_user(conn, "alice", "password-1")
    token = accounts.create_session(conn, uid)
    user, renewed = accounts.resolve_session(conn, token)
    assert user["id"] == uid and renewed is False
    accounts.delete_session(conn, token)
    assert accounts.resolve_session(conn, token) is None


def test_session_token_is_stored_hashed(conn):
    uid = accounts.create_user(conn, "alice", "password-1")
    token = accounts.create_session(conn, uid)
    stored = [r["token_hash"] for r in conn.execute("SELECT token_hash FROM sessions")]
    assert token not in stored and len(stored) == 1


def test_unknown_token(conn):
    assert accounts.resolve_session(conn, "nope") is None
    assert accounts.resolve_session(conn, "") is None


def test_session_expires(conn, clock):
    uid = accounts.create_user(conn, "alice", "password-1")
    token = accounts.create_session(conn, uid)
    clock.advance(timedelta(days=31))
    assert accounts.resolve_session(conn, token) is None


def test_session_renews_when_less_than_29_days_left(conn, clock):
    uid = accounts.create_user(conn, "alice", "password-1")
    token = accounts.create_session(conn, uid)
    clock.advance(timedelta(hours=12))
    assert accounts.resolve_session(conn, token)[1] is False  # 还剩 29.5 天，不写库
    clock.advance(timedelta(days=1))
    assert accounts.resolve_session(conn, token)[1] is True
    # 续期后从「现在」起再算 30 天
    clock.advance(timedelta(days=29, hours=23))
    assert accounts.resolve_session(conn, token) is not None


def test_deactivate_and_password_reset_revoke_sessions(conn):
    uid = accounts.create_user(conn, "alice", "password-1")
    t1 = accounts.create_session(conn, uid)
    accounts.set_password(conn, uid, "password-2")
    assert accounts.resolve_session(conn, t1) is None
    assert accounts.authenticate(conn, "alice", "password-2") is not None

    t2 = accounts.create_session(conn, uid)
    accounts.set_active(conn, uid, False)
    assert accounts.resolve_session(conn, t2) is None


def test_session_of_inactive_user_is_rejected_even_if_row_survives(conn):
    uid = accounts.create_user(conn, "alice", "password-1")
    token = accounts.create_session(conn, uid)
    conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (uid,))
    conn.commit()
    assert accounts.resolve_session(conn, token) is None


def test_purge_expired_sessions(conn, clock):
    uid = accounts.create_user(conn, "alice", "password-1")
    accounts.create_session(conn, uid)
    clock.advance(timedelta(days=31))
    accounts.create_session(conn, uid)
    accounts.purge_expired_sessions(conn)
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1


def test_admin_password_written_once(conn):
    assert not accounts.admin_configured(conn)
    assert accounts.set_admin_password_if_missing(conn, "admin-pass-1") is True
    assert accounts.set_admin_password_if_missing(conn, "admin-pass-2") is False
    assert accounts.verify_admin(conn, "admin-pass-1")
    assert not accounts.verify_admin(conn, "admin-pass-2")


def test_admin_session(conn, clock):
    accounts.set_admin_password_if_missing(conn, "admin-pass-1")
    token = accounts.create_admin_session(conn)
    assert accounts.check_admin_session(conn, token)
    assert not accounts.check_admin_session(conn, "other")
    clock.advance(timedelta(hours=13))
    assert not accounts.check_admin_session(conn, token)


def test_admin_logout(conn):
    accounts.set_admin_password_if_missing(conn, "admin-pass-1")
    token = accounts.create_admin_session(conn)
    accounts.delete_admin_session(conn, token)
    assert not accounts.check_admin_session(conn, token)


def test_meta(conn):
    assert accounts.get_meta(conn, "k") is None
    accounts.set_meta(conn, "k", "1")
    accounts.set_meta(conn, "k", "2")
    assert accounts.get_meta(conn, "k") == "2"
```

- [ ] **Step 3: 运行，确认失败**

Run: `cd backend && .venv/bin/pytest tests/test_accounts.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'accounts'`

- [ ] **Step 4: 实现 `backend/accounts.py`**

```python
"""账号库 accounts.db：用户、会话、管理员、一次性迁移标记。

业务数据在每个账号自己的库里（见 storage.py），这里只放身份相关的东西。
时间一律存 UTC 的 ISO 字符串，比较在 Python 里做。
"""
import hashlib
import hmac
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

import storage

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,32}$")
PASSWORD_MIN = 8
PASSWORD_MAX = 128

SESSION_TTL = timedelta(days=30)
# 剩余有效期低于它才续期：每个会话每天最多写一次库，而不是每个请求都写
SESSION_RENEW_BELOW = timedelta(days=29)
ADMIN_SESSION_TTL = timedelta(hours=12)

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1
_SCRYPT_DKLEN = 32


class UsernameTaken(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ 密码

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(hash_hex)
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


# 用户名不存在时也算一次哈希，让「账号不存在」和「密码错」耗时一致
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def _validate_password(password: str):
    if not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
        raise ValueError(f"密码长度需在 {PASSWORD_MIN}–{PASSWORD_MAX} 个字符之间")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ------------------------------------------------------------------ 连接与表结构

def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(storage.accounts_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_active     INTEGER NOT NULL DEFAULT 1,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS admin (
            id            INTEGER PRIMARY KEY CHECK (id = 1),
            password_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS admin_sessions (
            token_hash TEXT PRIMARY KEY,
            expires_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.commit()


# ------------------------------------------------------------------ 用户

def create_user(conn, username: str, password: str) -> int:
    if not USERNAME_RE.match(username or ""):
        raise ValueError("用户名只能是 3–32 位小写字母、数字或下划线")
    _validate_password(password)
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, hash_password(password)),
        )
    except sqlite3.IntegrityError:
        raise UsernameTaken(username)
    conn.commit()
    return cur.lastrowid


def get_user(conn, uid: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT id, username, is_active, created_at FROM users WHERE id = ?", (uid,)
    ).fetchone()


def list_users(conn) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, username, is_active, created_at FROM users ORDER BY id"
    ).fetchall()


def all_user_ids(conn) -> list[int]:
    return [r[0] for r in conn.execute("SELECT id FROM users ORDER BY id")]


def active_user_ids(conn) -> list[int]:
    return [r[0] for r in conn.execute("SELECT id FROM users WHERE is_active = 1 ORDER BY id")]


def authenticate(conn, username: str, password: str) -> Optional[sqlite3.Row]:
    row = conn.execute(
        "SELECT id, username, is_active, password_hash FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    ok = verify_password(password, row["password_hash"] if row else _DUMMY_HASH)
    if not row or not ok or not row["is_active"]:
        return None
    return row


def set_password(conn, uid: int, password: str):
    _validate_password(password)
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), uid)
    )
    # 改了密码，已登录的设备都要重新登录
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
    conn.commit()


def set_active(conn, uid: int, active: bool):
    conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if active else 0, uid))
    if not active:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
    conn.commit()


# ------------------------------------------------------------------ 会话

def create_session(conn, uid: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (_token_hash(token), uid, (_now() + SESSION_TTL).isoformat()),
    )
    conn.commit()
    return token


def resolve_session(conn, token: str):
    """返回 (用户行, 是否续期) 或 None。过期、账号停用都视为无效。"""
    if not token:
        return None
    th = _token_hash(token)
    row = conn.execute(
        "SELECT s.expires_at, u.id, u.username, u.is_active "
        "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
        (th,),
    ).fetchone()
    if not row or not row["is_active"]:
        return None
    now = _now()
    expires = datetime.fromisoformat(row["expires_at"])
    if expires <= now:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (th,))
        conn.commit()
        return None
    renewed = expires - now < SESSION_RENEW_BELOW
    if renewed:
        conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
            ((now + SESSION_TTL).isoformat(), th),
        )
        conn.commit()
    return row, renewed


def delete_session(conn, token: str):
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    conn.commit()


def purge_expired_sessions(conn):
    now = _now().isoformat()
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
    conn.execute("DELETE FROM admin_sessions WHERE expires_at <= ?", (now,))
    conn.commit()


# ------------------------------------------------------------------ 管理员

def admin_configured(conn) -> bool:
    return conn.execute("SELECT 1 FROM admin WHERE id = 1").fetchone() is not None


def set_admin_password_if_missing(conn, password: str) -> bool:
    """只在还没有管理员密码时写入：之后改环境变量不会覆盖。返回是否写入。"""
    cur = conn.execute(
        "INSERT OR IGNORE INTO admin (id, password_hash) VALUES (1, ?)",
        (hash_password(password),),
    )
    conn.commit()
    return cur.rowcount == 1


def verify_admin(conn, password: str) -> bool:
    row = conn.execute("SELECT password_hash FROM admin WHERE id = 1").fetchone()
    return verify_password(password, row["password_hash"] if row else _DUMMY_HASH) and row is not None


def create_admin_session(conn) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO admin_sessions (token_hash, expires_at) VALUES (?, ?)",
        (_token_hash(token), (_now() + ADMIN_SESSION_TTL).isoformat()),
    )
    conn.commit()
    return token


def check_admin_session(conn, token: str) -> bool:
    if not token:
        return False
    row = conn.execute(
        "SELECT expires_at FROM admin_sessions WHERE token_hash = ?", (_token_hash(token),)
    ).fetchone()
    return row is not None and datetime.fromisoformat(row["expires_at"]) > _now()


def delete_admin_session(conn, token: str):
    conn.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (_token_hash(token),))
    conn.commit()


# ------------------------------------------------------------------ meta

def get_meta(conn, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn, key: str, value: str):
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
```

- [ ] **Step 5: 运行，确认通过**

Run: `cd backend && .venv/bin/pytest tests/test_accounts.py -q`
Expected: 全部 PASS。再跑全量 `.venv/bin/pytest tests -q`，确认没有影响现有测试。

- [ ] **Step 6: Commit**

```bash
git add backend/storage.py backend/accounts.py backend/tests/test_accounts.py
git commit -m "Add accounts store with scrypt passwords and sessions"
```

---

### Task 2: 旧数据迁移与启动引导（storage 迁移 + bootstrap.py + database.init_db(path)）

**Files:**
- Modify: `backend/storage.py`（加 `provision_user`、`migrate_legacy_layout`）
- Modify: `backend/database.py`（`init_db(db_path)`、`connect(db_path)`；删除 `DB_PATH` 与 `get_db`）
- Modify: `backend/thumbnail.py`（函数改为接收上传目录）
- Create: `backend/bootstrap.py`
- Test: `backend/tests/test_storage_migration.py`、`backend/tests/test_thumbnail.py`

> 本任务改了 `database.get_db` 和 `thumbnail` 的签名，**现有路由与部分测试会暂时失败**，由 Task 3 修复。本任务只要求新测试和 `test_thumbnail.py`、`test_accounts.py` 通过；Task 2 与 Task 3 之间不要部署。

**Interfaces:**
- Consumes: Task 1 的 `storage.*` 路径函数、`accounts.*`
- Produces:
  - `database.connect(db_path: str) -> sqlite3.Connection`（Row、WAL、外键）；`database.init_db(db_path: str)`
  - `thumbnail.thumb_dir(upload_dir) -> str`、`thumbnail.generate_thumbnail(upload_dir, filename)`、`thumbnail.delete_thumbnail(upload_dir, filename)`、`thumbnail.migrate_existing(upload_dir)`
  - `storage.provision_user(uid)`：建目录 + `init_db`，幂等
  - `storage.migrate_legacy_layout(uid)`：把旧库与旧上传文件移给 uid，幂等；源与目标同时存在时抛 `storage.MigrationConflict`
  - `bootstrap.INITIAL_USERNAME = "babelingz"`、`bootstrap.LEGACY_FLAG = "legacy_migrated"`、`class bootstrap.BootstrapError(RuntimeError)`、`bootstrap.run() -> list[int]`（返回全部用户 id）

- [ ] **Step 1: 改 `thumbnail.py`，函数接收上传目录**

把模块顶部的 `UPLOAD_DIR`、`THUMB_DIR` 常量删掉，改成：

```python
import os
from PIL import Image, ImageOps

THUMB_SIZE = (800, 800)
THUMB_QUALITY = 85
# 标记文件：存在即表示「按 EXIF 摆正」的缩略图重建已经做过
# 以后若再批量重建缩略图，记得同步加大前端 src/thumbs.js 的 THUMB_VERSION，否则浏览器会继续显示缓存的旧图
ORIENTED_MARKER = ".oriented-v1"


def thumb_dir(upload_dir: str) -> str:
    return os.path.join(upload_dir, "thumbs")


def generate_thumbnail(upload_dir: str, filename: str):
    """Generate a thumbnail for the given filename. Skips non-image files."""
    src = os.path.join(upload_dir, filename)
    dst = os.path.join(thumb_dir(upload_dir), filename)
    os.makedirs(thumb_dir(upload_dir), exist_ok=True)
    # 以下 try 块与原来完全相同
    ...


def delete_thumbnail(upload_dir: str, filename: str):
    """Delete the thumbnail for the given filename if it exists."""
    path = os.path.join(thumb_dir(upload_dir), filename)
    if os.path.exists(path):
        os.remove(path)
```

（`...` 处保留原有的 `try: with Image.open(src) ... except Exception: pass` 块，一字不改。）`_needs_rotation` 不变。`migrate_existing` 改为：

```python
def migrate_existing(upload_dir: str):
    """Generate thumbnails for all existing images that don't have one yet.

    旧版本生成缩略图时没按 EXIF 摆正：第一次启动新版本时，把带方向标记的原图
    的缩略图重建一遍，做完写标记文件，以后不再重复。
    """
    tdir = thumb_dir(upload_dir)
    os.makedirs(tdir, exist_ok=True)
    marker = os.path.join(tdir, ORIENTED_MARKER)
    reorient = not os.path.exists(marker)
    for fname in os.listdir(upload_dir):
        src = os.path.join(upload_dir, fname)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(tdir, fname)
        if os.path.exists(dst) and not (reorient and _needs_rotation(src)):
            continue
        generate_thumbnail(upload_dir, fname)
    if reorient:
        with open(marker, "w"):
            pass
```

> 注意：先读一遍原 `migrate_existing` 的结尾，确认原来写标记文件的方式，保持一致；上面是等价写法。`ensure_thumb_dir` 删除。

- [ ] **Step 2: 改 `tests/test_thumbnail.py` 用新签名（不再依赖 client）**

```python
import os

from PIL import Image

import thumbnail


def _sideways_phone_jpeg(path, size=(1600, 1200)):
    """手机竖拍的存法：像素是横的，EXIF 标记「顺时针转 90°」。"""
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", size, (200, 30, 30)).save(path, "JPEG", exif=exif.tobytes())


def test_thumbnail_is_rotated_upright(tmp_path):
    up = str(tmp_path)
    _sideways_phone_jpeg(os.path.join(up, "portrait.jpg"))
    thumbnail.generate_thumbnail(up, "portrait.jpg")
    with Image.open(os.path.join(thumbnail.thumb_dir(up), "portrait.jpg")) as t:
        assert t.size == (600, 800)


def test_migrate_regenerates_stale_sideways_thumbnails_once(tmp_path):
    up = str(tmp_path)
    tdir = thumbnail.thumb_dir(up)
    os.makedirs(tdir)
    marker = os.path.join(tdir, thumbnail.ORIENTED_MARKER)
    _sideways_phone_jpeg(os.path.join(up, "old.jpg"))
    # 旧版本生成的缩略图：没摆正、也没有 EXIF
    Image.new("RGB", (800, 600)).save(os.path.join(tdir, "old.jpg"), "JPEG")

    thumbnail.migrate_existing(up)
    with Image.open(os.path.join(tdir, "old.jpg")) as t:
        assert t.size == (600, 800)
    assert os.path.exists(marker)

    # 已迁移过：再跑一次不会重新生成（这里故意放回横的，验证不被改动）
    Image.new("RGB", (800, 600)).save(os.path.join(tdir, "old.jpg"), "JPEG")
    thumbnail.migrate_existing(up)
    with Image.open(os.path.join(tdir, "old.jpg")) as t:
        assert t.size == (800, 600)
```

Run: `cd backend && .venv/bin/pytest tests/test_thumbnail.py -q` → PASS

- [ ] **Step 3: 改 `database.py`**

删除 `import os` 以外对 `DB_PATH` 的定义和整个 `get_db` 生成器，新增 `connect`，`init_db` 接收路径：

```python
import sqlite3
import os


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    # 以下从 conn.executescript(...) 到 conn.close() 与原来完全相同
```

`_init_custom_fields`、`_init_image_embeddings`、迁移函数都不动。

- [ ] **Step 4: 写失败的测试 `backend/tests/test_storage_migration.py`**

```python
import os
import sqlite3

import pytest

import accounts
import bootstrap
import database
import storage
import thumbnail


@pytest.fixture()
def layout(tmp_path, monkeypatch):
    """一套独立的 data/ 与 uploads/，不碰 conftest 的全局目录。"""
    data = tmp_path / "data"
    uploads = tmp_path / "uploads"
    data.mkdir()
    uploads.mkdir()
    monkeypatch.setattr(storage, "DATA_DIR", str(data))
    monkeypatch.setattr(storage, "UPLOAD_ROOT", str(uploads))
    monkeypatch.setenv("INITIAL_USER_PASSWORD", "initial-pass-1")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    return data, uploads


def _make_legacy(data, uploads):
    """造一个单用户时代的部署：旧库里有一条日志一张图，上传目录有原图、缩略图和标记文件。"""
    db = str(data / "piclog.db")
    database.init_db(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO categories (id, name) VALUES (7, '手套')")
    conn.execute("INSERT INTO logs (id, category_id, description) VALUES (42, 7, '旧日志')")
    conn.execute("INSERT INTO images (id, log_id, filename, original_name) VALUES (9, 42, 'abc.jpg', 'a.jpg')")
    conn.commit()
    conn.close()
    (uploads / "abc.jpg").write_bytes(b"original")
    (uploads / "thumbs").mkdir()
    (uploads / "thumbs" / "abc.jpg").write_bytes(b"thumb")
    (uploads / "thumbs" / thumbnail.ORIENTED_MARKER).write_bytes(b"")


def _user1_rows():
    conn = sqlite3.connect(storage.user_db_path(1))
    rows = conn.execute("SELECT l.id, l.description, i.id, i.filename FROM logs l JOIN images i ON i.log_id = l.id").fetchall()
    conn.close()
    return rows


def test_legacy_data_moves_to_first_user(layout):
    data, uploads = layout
    _make_legacy(data, uploads)

    assert bootstrap.run() == [1]

    assert not (data / "piclog.db").exists()
    assert _user1_rows() == [(42, "旧日志", 9, "abc.jpg")]  # ID 与文件名不变
    up1 = storage.user_upload_dir(1)
    assert open(os.path.join(up1, "abc.jpg"), "rb").read() == b"original"
    assert open(os.path.join(up1, "thumbs", "abc.jpg"), "rb").read() == b"thumb"
    # 标记文件跟着搬走：不会因为「没有标记」再把所有缩略图重建一遍
    assert os.path.exists(os.path.join(up1, "thumbs", thumbnail.ORIENTED_MARKER))
    assert not (uploads / "abc.jpg").exists()
    assert not (uploads / "thumbs").exists()

    conn = accounts.connect()
    user = accounts.authenticate(conn, "babelingz", "initial-pass-1")
    assert user["id"] == 1
    assert accounts.get_meta(conn, bootstrap.LEGACY_FLAG) == "1"
    conn.close()


def test_second_run_changes_nothing(layout):
    data, uploads = layout
    _make_legacy(data, uploads)
    bootstrap.run()
    # 迁移完成后，有人在旧位置又放了个库：不能再被搬
    database.init_db(str(data / "piclog.db"))
    assert bootstrap.run() == [1]
    assert (data / "piclog.db").exists()
    assert _user1_rows() == [(42, "旧日志", 9, "abc.jpg")]


def test_resume_after_partial_move(layout):
    """模拟上次在移动途中断电：库已经移走、原图还在旧位置、账号还没建。"""
    data, uploads = layout
    _make_legacy(data, uploads)
    os.makedirs(storage.user_dir(1))
    os.replace(data / "piclog.db", storage.user_db_path(1))

    assert bootstrap.run() == [1]
    assert _user1_rows() == [(42, "旧日志", 9, "abc.jpg")]
    assert os.path.exists(os.path.join(storage.user_upload_dir(1), "abc.jpg"))


def test_conflict_refuses_to_overwrite(layout):
    data, uploads = layout
    _make_legacy(data, uploads)
    os.makedirs(storage.user_upload_dir(1))
    with open(os.path.join(storage.user_upload_dir(1), "abc.jpg"), "wb") as f:
        f.write(b"someone copied this by hand")

    with pytest.raises(storage.MigrationConflict, match="abc.jpg"):
        bootstrap.run()
    assert (uploads / "abc.jpg").read_bytes() == b"original"


def test_fresh_deploy_creates_empty_first_user(layout):
    assert bootstrap.run() == [1]
    conn = sqlite3.connect(storage.user_db_path(1))
    assert conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0] == 0
    conn.close()
    assert os.path.isdir(os.path.join(storage.user_upload_dir(1), "thumbs"))


def test_missing_initial_password_fails_before_moving_anything(layout, monkeypatch):
    data, uploads = layout
    _make_legacy(data, uploads)
    monkeypatch.delenv("INITIAL_USER_PASSWORD")
    with pytest.raises(bootstrap.BootstrapError, match="INITIAL_USER_PASSWORD"):
        bootstrap.run()
    assert (data / "piclog.db").exists()
    assert (uploads / "abc.jpg").exists()


def test_initial_password_not_needed_once_users_exist(layout, monkeypatch):
    bootstrap.run()
    monkeypatch.delenv("INITIAL_USER_PASSWORD")
    assert bootstrap.run() == [1]


def test_admin_password_written_once_from_env(layout, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    bootstrap.run()
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-2")
    bootstrap.run()
    conn = accounts.connect()
    assert accounts.verify_admin(conn, "admin-pass-1")
    assert not accounts.verify_admin(conn, "admin-pass-2")
    conn.close()


def test_every_user_db_is_initialised_on_startup(layout):
    bootstrap.run()
    conn = accounts.connect()
    uid = accounts.create_user(conn, "second", "password-2")
    conn.close()
    # 模拟新用户的库文件被删（或新建时开户失败）：下次启动会补上
    assert bootstrap.run() == [1, uid]
    assert os.path.isfile(storage.user_db_path(uid))


def test_provision_user_is_idempotent(layout):
    storage.provision_user(5)
    conn = sqlite3.connect(storage.user_db_path(5))
    conn.execute("INSERT INTO categories (name) VALUES ('x')")
    conn.commit()
    conn.close()
    storage.provision_user(5)
    conn = sqlite3.connect(storage.user_db_path(5))
    assert conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 1
    conn.close()
```

Run: `cd backend && .venv/bin/pytest tests/test_storage_migration.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'bootstrap'`

- [ ] **Step 5: 在 `storage.py` 末尾加开户与迁移**

在文件顶部 import 区加 `import database` 和 `import thumbnail`，末尾追加：

```python
class MigrationConflict(RuntimeError):
    pass


def provision_user(uid: int):
    """建好账号的目录和库。幂等：已有的库只会跑一遍 init_db 的增量迁移。"""
    os.makedirs(thumbnail.thumb_dir(user_upload_dir(uid)), exist_ok=True)
    database.init_db(user_db_path(uid))


def _move(src: str, dst: str):
    if not os.path.exists(src):
        return  # 上次已经搬过
    if os.path.exists(dst):
        # 两边都有说明有人手工动过：宁可起不来，也不能覆盖掉任何一边
        raise MigrationConflict(f"迁移冲突：{src} 与 {dst} 同时存在，请人工确认后删掉其中一个")
    os.replace(src, dst)


def migrate_legacy_layout(uid: int):
    """把单用户时代的库和上传文件整体移给 uid。

    同一个卷内用 rename，不复制、不占额外空间。每个文件单独判断，
    中途断电后再跑一遍会接着搬剩下的。
    """
    os.makedirs(user_dir(uid), exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        _move(legacy_db_path() + suffix, user_db_path(uid) + suffix)

    dest = user_upload_dir(uid)
    dest_thumbs = thumbnail.thumb_dir(dest)
    os.makedirs(dest_thumbs, exist_ok=True)
    if not os.path.isdir(UPLOAD_ROOT):
        return
    for name in os.listdir(UPLOAD_ROOT):
        src = os.path.join(UPLOAD_ROOT, name)
        if os.path.isfile(src):
            _move(src, os.path.join(dest, name))
    legacy_thumbs = thumbnail.thumb_dir(UPLOAD_ROOT)
    if os.path.isdir(legacy_thumbs):
        for name in os.listdir(legacy_thumbs):
            src = os.path.join(legacy_thumbs, name)
            if os.path.isfile(src):
                _move(src, os.path.join(dest_thumbs, name))
        try:
            os.rmdir(legacy_thumbs)
        except OSError:
            pass  # 里面还有子目录之类的意外内容：留着，不影响运行
```

- [ ] **Step 6: 实现 `backend/bootstrap.py`**

```python
"""启动引导：每次启动都跑，里面的每一步都是幂等的。

1. 建 accounts.db 的表
2. 首次升级：把单用户时代的数据移给 1 号账号，并创建 babelingz
3. 首次配置管理员密码
4. 对每个账号的库跑 init_db（表结构增量迁移），补全缩略图
"""
import logging
import os

import accounts
import storage
import thumbnail

log = logging.getLogger("piclog.bootstrap")

INITIAL_USERNAME = "babelingz"
LEGACY_FLAG = "legacy_migrated"


class BootstrapError(RuntimeError):
    pass


def run() -> list[int]:
    os.makedirs(storage.DATA_DIR, exist_ok=True)
    conn = accounts.connect()
    try:
        accounts.init_schema(conn)
        need_first_user = not accounts.all_user_ids(conn)
        initial_password = os.environ.get("INITIAL_USER_PASSWORD", "")
        # 先检查再动文件：缺配置时旧数据原封不动
        if need_first_user and not initial_password:
            raise BootstrapError(
                f"缺少环境变量 INITIAL_USER_PASSWORD：首次启动需要它来创建账号 {INITIAL_USERNAME}"
            )

        if accounts.get_meta(conn, LEGACY_FLAG) != "1":
            # 旧数据归 1 号账号。先搬文件再建账号：账号建好以后就不会再走到这里的
            # 「需要建首个账号」分支，搬到一半断电的话下次启动仍会接着搬
            storage.migrate_legacy_layout(1)
            if need_first_user:
                uid = accounts.create_user(conn, INITIAL_USERNAME, initial_password)
                if uid != 1:
                    raise BootstrapError(f"首个账号的 id 应为 1，实际为 {uid}")
            accounts.set_meta(conn, LEGACY_FLAG, "1")

        admin_password = os.environ.get("ADMIN_PASSWORD", "")
        if admin_password and accounts.set_admin_password_if_missing(conn, admin_password):
            log.info("已写入管理员密码")

        user_ids = accounts.all_user_ids(conn)
    finally:
        conn.close()

    for uid in user_ids:
        storage.provision_user(uid)
        thumbnail.migrate_existing(storage.user_upload_dir(uid))
    return user_ids
```

> 注意 `need_first_user` 为真但迁移标记已是 `"1"` 的情况不存在（标记只在建号之后写）。

- [ ] **Step 7: 运行新测试**

Run: `cd backend && .venv/bin/pytest tests/test_storage_migration.py tests/test_accounts.py tests/test_thumbnail.py -q`
Expected: 全部 PASS（其他测试此时会因 `database.get_db` 被删而失败，属预期，Task 3 修复）

- [ ] **Step 8: Commit**

```bash
git add backend/storage.py backend/bootstrap.py backend/database.py backend/thumbnail.py backend/tests/test_storage_migration.py backend/tests/test_thumbnail.py
git commit -m "Add per-user storage layout and one-time legacy migration"
```

---

### Task 3: 路由切换到按用户的库与目录（暂时固定为 1 号用户）

**Files:**
- Create: `backend/deps.py`
- Create: `backend/routers/files.py`
- Modify: `backend/routers/categories.py`、`fields.py`、`logs.py`、`images.py`、`search.py`
- Modify: `backend/indexer.py`
- Modify: `backend/main.py`
- Modify: `backend/tests/conftest.py`、`tests/test_migration.py`、`tests/test_indexer.py`、`tests/test_image_search.py`
- Create: `backend/tests/test_files.py`
- Modify: `docs/superpowers/specs/2026-09-29-multi-user-design.md`

**Interfaces:**
- Consumes: Task 2 的 `database.connect/init_db`、`thumbnail.*(upload_dir, ...)`、`storage.*`、`bootstrap.run`、`accounts.active_user_ids`
- Produces:
  - `deps.current_user_id() -> int`（本任务临时返回 1，Task 4 换成按会话）
  - `deps.get_db`（生成器依赖，yield 当前用户库的连接；库文件不存在返回 500）
  - `deps.get_upload_dir() -> str`
  - `indexer.count_pending(conn, user_id: int) -> int`、`indexer.process_pending() -> int`（遍历所有启用账号）、`indexer.notify()`（签名不变）
  - `GET /api/files/{filename}`、`GET /api/files/thumbs/{filename}`
  - conftest：`db_conn` 打开 `storage.user_db_path(1)`

- [ ] **Step 1: 创建 `backend/deps.py`（临时版本）**

```python
"""请求级依赖：当前是谁、他的库、他的上传目录。

所有业务路由都通过这里的 get_db / get_upload_dir 访问数据，
按账号隔离就收口在这一个文件里。
"""
import logging
import os

from fastapi import Depends, HTTPException

import database
import storage

log = logging.getLogger("piclog.deps")


def current_user_id() -> int:
    # 临时：Task 4 换成从会话 Cookie 识别
    return 1


def get_db(user_id: int = Depends(current_user_id)):
    path = storage.user_db_path(user_id)
    # sqlite3.connect 遇到不存在的文件会静默建一个空库，那样用户会看到「数据全没了」
    if not os.path.isfile(path):
        log.error("用户 %s 的库不存在：%s", user_id, path)
        raise HTTPException(500, "用户数据不可用")
    conn = database.connect(path)
    try:
        yield conn
    finally:
        conn.close()


def get_upload_dir(user_id: int = Depends(current_user_id)) -> str:
    return storage.user_upload_dir(user_id)
```

- [ ] **Step 2: 路由改用 deps**

`routers/categories.py`、`routers/fields.py`、`routers/search.py`：把 `from database import get_db` 改成 `from deps import get_db`。

`routers/images.py`：
- `from database import get_db` → `from deps import get_db, get_upload_dir`
- 删除模块常量 `UPLOAD_DIR = ...`
- `upload_images` 参数加 `upload_dir: str = Depends(get_upload_dir),`，函数体里 `UPLOAD_DIR` 全部换成 `upload_dir`，`generate_thumbnail(stored_name)` → `generate_thumbnail(upload_dir, stored_name)`
- `delete_image` 参数加 `upload_dir: str = Depends(get_upload_dir),`，`os.path.join(UPLOAD_DIR, ...)` → `os.path.join(upload_dir, ...)`，`delete_thumbnail(row["filename"])` → `delete_thumbnail(upload_dir, row["filename"])`

`routers/logs.py`：
- `from database import get_db` → `from deps import get_db, get_upload_dir`
- 删除模块常量 `UPLOAD_DIR = ...`
- `create_log` 参数加 `upload_dir: str = Depends(get_upload_dir),`；函数体中 `os.makedirs(UPLOAD_DIR, ...)`、`os.path.join(UPLOAD_DIR, ...)` 换成 `upload_dir`；`generate_thumbnail(stored_name)` → `generate_thumbnail(upload_dir, stored_name)`

`routers/search.py`：
- 加 `from deps import current_user_id, get_db`
- `search_by_image` 参数加 `user_id: int = Depends(current_user_id),`
- 返回处 `indexer.count_pending(db)` → `indexer.count_pending(db, user_id)`

- [ ] **Step 3: 改 `indexer.py` 为逐用户扫描**

替换 import 与全部函数（保留模块 docstring、`_MISSING_SQL`、`notify`、`_loop`、`start`）：

```python
import logging
import os
import sqlite3
import threading

from PIL import Image, ImageOps

import accounts
import embedding
import storage
import thumbnail

log = logging.getLogger("piclog.indexer")

_wake = threading.Event()
_thread = None
# 解码失败的 (user_id, image_id)（非图片、文件损坏）。各账号的库 id 会重复，所以带上 user_id。
# 只记在内存里：重启后会再试一次
_failed: set[tuple[int, int]] = set()

# _MISSING_SQL 不变


def _missing(conn, user_id: int) -> list[tuple[int, str]]:
    rows = conn.execute(_MISSING_SQL, (embedding.MODEL_ID,)).fetchall()
    return [(r[0], r[1]) for r in rows if (user_id, r[0]) not in _failed]


def count_pending(conn, user_id: int) -> int:
    """属于有效日志、还没有当前模型向量、且没有解码失败过的图片数。"""
    return len(_missing(conn, user_id))


def _open_image(upload_dir: str, filename: str) -> Image.Image:
    # 优先用 800px 缩略图：解码快得多，模型输入只有 224px，效果没有差别
    thumb = os.path.join(thumbnail.thumb_dir(upload_dir), filename)
    path = thumb if os.path.isfile(thumb) else os.path.join(upload_dir, filename)
    img = Image.open(path)
    img.load()
    # 缩略图已摆正（EXIF 已去掉，这里是空操作）；回退到原图时要按 EXIF 摆正，
    # 与查询照片保持一致
    return ImageOps.exif_transpose(img)


def _process_user(user_id: int) -> tuple[int, bool]:
    """补算一个账号缺向量的图片。返回 (写入条数, 是否因模型不可用而中止)。"""
    upload_dir = storage.user_upload_dir(user_id)
    conn = sqlite3.connect(storage.user_db_path(user_id))
    conn.execute("PRAGMA foreign_keys=ON")
    done = 0
    try:
        for image_id, filename in _missing(conn, user_id):
            try:
                img = _open_image(upload_dir, filename)
                vec = embedding.embed(img)
            except embedding.EmbeddingUnavailable:
                log.exception("模型不可用，停止本轮补算")
                return done, True
            except Exception:
                log.warning("用户 %s 的图片 %s（%s）无法解码，跳过", user_id, image_id, filename)
                _failed.add((user_id, image_id))
                continue
            # 推理要好几秒，这期间图片可能已被删除：只在 images 行还在时写入，
            # 否则外键约束会让 INSERT 报错
            cur = conn.execute(
                "INSERT OR REPLACE INTO image_embeddings (image_id, model, vector) "
                "SELECT ?, ?, ? WHERE EXISTS (SELECT 1 FROM images WHERE id = ?)",
                (image_id, embedding.MODEL_ID, embedding.to_blob(vec), image_id),
            )
            conn.commit()
            done += cur.rowcount
    finally:
        conn.close()
    return done, False


def process_pending() -> int:
    """依次为每个启用账号补算缺向量的图片，返回本次写入的总条数。

    只有一个线程、账号串行处理：NAS 的 CPU 扛不住并发推理。
    停用账号跳过，重新启用后下一轮自然补上。
    """
    if not embedding.available():
        return 0
    conn = accounts.connect()
    try:
        user_ids = accounts.active_user_ids(conn)
    finally:
        conn.close()
    total = 0
    for uid in user_ids:
        if not os.path.isfile(storage.user_db_path(uid)):
            log.warning("用户 %s 的库不存在，跳过", uid)
            continue
        try:
            done, stopped = _process_user(uid)
        except Exception:
            # 一个账号的库坏了不能拖累其他账号
            log.exception("用户 %s 建立索引失败，跳过", uid)
            continue
        total += done
        if stopped:
            break
    return total
```

`reset_state()` 不变（`_failed.clear()`）。删除 `import database` 和 `from thumbnail import THUMB_DIR, UPLOAD_DIR`。

- [ ] **Step 4: 创建 `backend/routers/files.py`**

```python
"""图片文件：只能读当前账号库里登记过的文件。

文件名必须等于本账号 images 表中的某个 filename —— 这一条同时挡住了
路径穿越和读别人的文件，比校验文件名格式更严格（旧数据的扩展名来自用户的
原始文件名，格式并不统一）。
"""
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

import thumbnail
from deps import get_db, get_upload_dir

router = APIRouter(prefix="/api/files", tags=["files"])

# 文件名是 uuid，内容永不改变；private：不允许中间代理缓存
CACHE_HEADERS = {"Cache-Control": "private, max-age=31536000"}


def _serve(db: sqlite3.Connection, directory: str, filename: str) -> FileResponse:
    known = db.execute("SELECT 1 FROM images WHERE filename = ?", (filename,)).fetchone()
    path = os.path.join(directory, filename)
    if not known or os.path.basename(filename) != filename or not os.path.isfile(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path, headers=CACHE_HEADERS)


# 必须先于 /{filename} 注册（虽然 {filename} 不匹配斜杠，顺序写清楚更稳）
@router.get("/thumbs/{filename}")
def get_thumbnail(
    filename: str,
    db: sqlite3.Connection = Depends(get_db),
    upload_dir: str = Depends(get_upload_dir),
):
    return _serve(db, thumbnail.thumb_dir(upload_dir), filename)


@router.get("/{filename}")
def get_original(
    filename: str,
    db: sqlite3.Connection = Depends(get_db),
    upload_dir: str = Depends(get_upload_dir),
):
    return _serve(db, upload_dir, filename)
```

- [ ] **Step 5: 改 `main.py`**

```python
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import bootstrap
import indexer
from routers import categories, logs, images, fields, search, files

STATIC_DIR = os.environ.get("STATIC_DIR", "/app/static")

app = FastAPI(title="PicLog")

app.include_router(categories.router)
app.include_router(logs.router)
app.include_router(images.router)
app.include_router(fields.router)
app.include_router(search.router)
app.include_router(files.router)


@app.on_event("startup")
def startup():
    bootstrap.run()
    indexer.start()
```

SPA 部分（`if os.path.isdir(STATIC_DIR): ...`）不变。删除 `UPLOAD_DIR`、`os.makedirs(UPLOAD_DIR...)`、`app.mount("/uploads", ...)`、`from database import init_db`、`from thumbnail import migrate_existing`。

- [ ] **Step 6: 改 `tests/conftest.py`**

顶部环境变量段改为：

```python
_TMP = tempfile.mkdtemp(prefix="piclog-test-")
os.environ["DB_PATH"] = os.path.join(_TMP, "data", "piclog.db")
os.environ["UPLOAD_DIR"] = os.path.join(_TMP, "uploads")
os.environ["INITIAL_USER_PASSWORD"] = "test-password-1"
os.environ.pop("ADMIN_PASSWORD", None)
os.environ.pop("ADMIN_PATH", None)
# （STATIC_DIR、MODEL_PATH、INDEXER_THREAD 三段保持原样）
```

import 段加 `import shutil`，把 `import database` 换成 `import storage`。`_reset_db` 改为：

```python
def _reset_storage():
    for d in (storage.DATA_DIR, storage.UPLOAD_ROOT):
        shutil.rmtree(d, ignore_errors=True)
```

`client` fixture 里调用 `_reset_storage()`。`db_conn` fixture 改为：

```python
@pytest.fixture()
def db_conn():
    conn = sqlite3.connect(storage.user_db_path(1))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    yield conn
    conn.close()
```

- [ ] **Step 7: 改现有测试里对旧全局路径的引用**

`tests/test_migration.py`：把所有 `database.init_db()` 替换成 `database.init_db(storage.user_db_path(1))`，并在顶部 `import database` 下加 `import storage`：

```bash
cd backend && sed -i '' 's/database\.init_db()/database.init_db(storage.user_db_path(1))/' tests/test_migration.py
```

`tests/test_indexer.py`：
- 顶部加 `import storage`
- `test_image_deleted_during_inference_is_not_written` 中 `sqlite3.connect(database.DB_PATH)` → `sqlite3.connect(storage.user_db_path(1))`
- 所有 `indexer.count_pending(db_conn)` → `indexer.count_pending(db_conn, 1)`
- `test_indexed_images_are_rotated_upright` 中 `os.path.join(thumbnail.THUMB_DIR, image["filename"])` → `os.path.join(thumbnail.thumb_dir(storage.user_upload_dir(1)), image["filename"])`
- 若 `import database` 不再使用则删除

`tests/test_image_search.py` 的 `test_constant_number_of_queries`：

```python
def test_constant_number_of_queries(client, gallery):
    """回归护栏：SQL 语句数不随命中条数增长（同 test_log_filter_sort 的做法）。"""
    import deps
    import storage
    from main import app

    statements = []

    def tracing_db():
        conn = sqlite3.connect(storage.user_db_path(1), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.set_trace_callback(statements.append)
        try:
            yield conn
        finally:
            conn.close()

    def run(min_score):
        statements.clear()
        app.dependency_overrides[deps.get_db] = tracing_db
        try:
            resp = search(client, solid_image_bytes(RED), min_score=min_score)
        finally:
            app.dependency_overrides.pop(deps.get_db, None)
        return len(resp.json()["items"]), len(statements)
    # 其余不变
```

然后全局搜一遍残留：

Run: `cd backend && grep -rn "database.DB_PATH\|database.get_db\|THUMB_DIR\|thumbnail.UPLOAD_DIR" tests/ *.py routers/`
Expected: 无输出

- [ ] **Step 8: 给多用户索引补测试（追加到 `tests/test_indexer.py` 末尾）**

```python
def _second_user(username="second"):
    import accounts
    conn = accounts.connect()
    uid = accounts.create_user(conn, username, "password-2")
    conn.close()
    storage.provision_user(uid)
    return uid


def _insert_image_for(uid, color):
    """绕过 HTTP 直接给某个账号放一张图（Task 4 之前还没有第二个会话）。"""
    import uuid
    name = f"{uuid.uuid4().hex}.png"
    up = storage.user_upload_dir(uid)
    with open(os.path.join(up, name), "wb") as f:
        f.write(solid_image_bytes(color))
    conn = sqlite3.connect(storage.user_db_path(uid))
    cid = conn.execute("INSERT INTO categories (name) VALUES ('c')").lastrowid
    lid = conn.execute("INSERT INTO logs (category_id) VALUES (?)", (cid,)).lastrowid
    iid = conn.execute(
        "INSERT INTO images (log_id, filename, original_name) VALUES (?, ?, 'x.png')", (lid, name)
    ).lastrowid
    conn.commit()
    conn.close()
    return iid


def _vectors(uid):
    conn = sqlite3.connect(storage.user_db_path(uid))
    rows = conn.execute("SELECT image_id FROM image_embeddings ORDER BY image_id").fetchall()
    conn.close()
    return [r[0] for r in rows]


def test_each_user_gets_own_index(client, fake_embedder, log_id):
    [mine] = upload(client, log_id, png("a.png", RED))
    other = _second_user()
    theirs = _insert_image_for(other, BLUE)

    assert indexer.process_pending() == 2
    assert _vectors(1) == [mine["id"]]
    assert _vectors(other) == [theirs]


def test_inactive_user_is_skipped_until_reactivated(client, fake_embedder):
    import accounts
    other = _second_user()
    _insert_image_for(other, BLUE)
    conn = accounts.connect()
    accounts.set_active(conn, other, False)
    assert indexer.process_pending() == 0
    accounts.set_active(conn, other, True)
    conn.close()
    assert indexer.process_pending() == 1


def test_failed_image_ids_are_tracked_per_user(client, fake_embedder, log_id):
    """两个账号都有 id=1 的图：一个解码失败，不能连累另一个。"""
    upload(client, log_id, ("notes.txt", b"not an image", "text/plain"))
    other = _second_user()
    _insert_image_for(other, BLUE)
    assert indexer.process_pending() == 1
    assert _vectors(other) == [1]


def test_broken_user_db_does_not_stop_others(client, fake_embedder, log_id):
    upload(client, log_id, png("a.png", RED))
    other = _second_user()
    with open(storage.user_db_path(other), "wb") as f:
        f.write(b"this is not sqlite")
    assert indexer.process_pending() == 1
```

注意：`test_each_user_gets_own_index` 依赖 `log_id` fixture 在 1 号账号下建日志；`test_failed_image_ids_are_tracked_per_user` 里 1 号账号的 txt 图片 id 是 1，第二个账号的图片 id 也是 1。

- [ ] **Step 9: 写 `tests/test_files.py`**

```python
import os

import storage
import thumbnail
from tests.helpers import RED, solid_image_bytes


def _log_with_image(client):
    cid = client.post("/api/categories", json={"name": "手套"}).json()["id"]
    resp = client.post(
        "/api/logs",
        data={"category_id": cid},
        files=[("files", ("a.png", solid_image_bytes(RED), "image/png"))],
    )
    assert resp.status_code == 201
    return resp.json()["images"][0]["filename"]


def test_original_and_thumbnail_are_served(client):
    name = _log_with_image(client)
    resp = client.get(f"/api/files/{name}")
    assert resp.status_code == 200
    assert resp.content == solid_image_bytes(RED)
    assert "private" in resp.headers["cache-control"]
    thumb = client.get(f"/api/files/thumbs/{name}")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/png" or thumb.content[:2] == b"\xff\xd8"


def test_file_on_disk_but_not_in_db_is_404(client):
    _log_with_image(client)
    up = storage.user_upload_dir(1)
    with open(os.path.join(up, "stray.png"), "wb") as f:
        f.write(b"x")
    assert client.get("/api/files/stray.png").status_code == 404


def test_path_traversal_is_404(client):
    _log_with_image(client)
    for path in (
        "/api/files/..%2F..%2F..%2Fdata%2Faccounts.db",
        "/api/files/%2E%2E",
        "/api/files/thumbs/..%2Fabc",
    ):
        assert client.get(path).status_code == 404, path


def test_old_static_uploads_route_is_gone(client):
    name = _log_with_image(client)
    assert client.get(f"/uploads/{name}").status_code == 404
    assert client.get(f"/uploads/thumbs/{name}").status_code == 404


def test_files_with_unusual_legacy_extension_are_served(client, db_conn):
    """旧数据的扩展名来自用户原始文件名，不一定规整。"""
    name = "0123456789abcdef0123456789abcdef.jpg(1)"
    up = storage.user_upload_dir(1)
    with open(os.path.join(up, name), "wb") as f:
        f.write(b"legacy")
    cid = db_conn.execute("INSERT INTO categories (name) VALUES ('c')").lastrowid
    lid = db_conn.execute("INSERT INTO logs (category_id) VALUES (?)", (cid,)).lastrowid
    db_conn.execute(
        "INSERT INTO images (log_id, filename, original_name) VALUES (?, ?, 'x')", (lid, name)
    )
    db_conn.commit()
    assert client.get(f"/api/files/{name}").content == b"legacy"
```

（`thumbnail` import 若未用到可删除。）

- [ ] **Step 10: 跑全量测试**

Run: `cd backend && .venv/bin/pytest tests -q`
Expected: 全部 PASS（129 个原有 + 新增）

- [ ] **Step 11: 把 spec 的两处细化写回 spec**

在 `docs/superpowers/specs/2026-09-29-multi-user-design.md`：
- 「图片文件」小节中把「文件名必须匹配 `^[0-9a-f]{32}...`，否则返回 404，杜绝路径穿越」改为「文件名必须等于当前用户库 `images.filename` 中登记过的某一项（且不含路径分隔），否则返回 404。旧数据的扩展名来自原始文件名、格式不统一，所以不用正则」
- 「失败处理」小节中把「同一 IP 连续失败 5 次」改为「同一 IP 对同一用户名连续失败 5 次（管理员登录按 IP）。按 (IP, 用户名) 计数是因为 Docker 端口映射可能让所有客户端显示为同一网关 IP，只按 IP 会一人输错锁住所有人」

- [ ] **Step 12: Commit**

```bash
git add backend docs/superpowers/specs/2026-09-29-multi-user-design.md
git commit -m "Serve every request from a per-user database and upload directory"
```

---

### Task 4: 登录与会话

**Files:**
- Create: `backend/ratelimit.py`
- Create: `backend/routers/auth.py`
- Modify: `backend/deps.py`（`current_user` 按会话识别；Cookie 工具）
- Modify: `backend/models.py`（`LoginIn`、`MeOut`）
- Modify: `backend/main.py`（挂 auth 路由）
- Modify: `backend/tests/conftest.py`（`client` 自动登录；`anon_client`、`make_user`、重置限流）
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: `accounts.*`（Task 1）、`storage.provision_user`
- Produces:
  - `ratelimit.allowed(key: tuple) -> bool`、`ratelimit.record_failure(key)`、`ratelimit.record_success(key)`、`ratelimit.reset()`、常量 `MAX_FAILURES = 5`、`LOCK_SECONDS = 900`、`ratelimit._clock`（可 monkeypatch）
  - `deps.SESSION_COOKIE = "piclog_session"`、`deps.set_session_cookie(response, token)`、`deps.clear_session_cookie(response)`、`deps.current_user(request, response) -> Row`、`deps.current_user_id(user) -> int`、`deps.client_ip(request) -> str`
  - 路由：`POST /api/auth/login` → `{"username"}`；`POST /api/auth/logout` → 204；`GET /api/auth/me` → `{"username"}`；`GET /api/health` → `{"status": "ok"}`
  - conftest：`client`（已以 babelingz 登录）、`anon_client`（未登录）、`make_user(username, password="password-2") -> TestClient`（已登录的新账号客户端）、常量 `TEST_PASSWORD = "test-password-1"`

- [ ] **Step 1: 写失败的测试 `backend/tests/test_auth.py`**

```python
from datetime import timedelta

import pytest

import accounts
import ratelimit
from tests.conftest import TEST_PASSWORD


def login(c, username="babelingz", password=TEST_PASSWORD):
    return c.post("/api/auth/login", json={"username": username, "password": password})


def test_health_needs_no_login(anon_client):
    assert anon_client.get("/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/api/categories", "/api/logs", "/api/auth/me"])
def test_business_api_requires_login(anon_client, path):
    assert anon_client.get(path).status_code == 401


def test_login_sets_httponly_cookie(anon_client):
    resp = login(anon_client)
    assert resp.status_code == 200
    assert resp.json() == {"username": "babelingz"}
    cookie = resp.headers["set-cookie"]
    assert "piclog_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie or "SameSite=Lax" in cookie
    assert "Max-Age=2592000" in cookie
    assert anon_client.get("/api/auth/me").json() == {"username": "babelingz"}
    assert anon_client.get("/api/categories").status_code == 200


@pytest.mark.parametrize("username,password", [
    ("babelingz", "wrong-password"),
    ("nobody", TEST_PASSWORD),
])
def test_bad_credentials_give_same_message(anon_client, username, password):
    resp = login(anon_client, username, password)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "账号或密码错误"


def test_logout(client):
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_logout_without_session_is_fine(anon_client):
    assert anon_client.post("/api/auth/logout").status_code == 204


def test_deactivated_user_session_is_rejected(client):
    conn = accounts.connect()
    accounts.set_active(conn, 1, False)
    conn.close()
    assert client.get("/api/categories").status_code == 401
    assert login(client).status_code == 401


def test_password_reset_revokes_sessions(client):
    conn = accounts.connect()
    accounts.set_password(conn, 1, "new-password-1")
    conn.close()
    assert client.get("/api/categories").status_code == 401
    assert login(client, password="new-password-1").status_code == 200


def test_session_is_renewed_with_new_cookie(client, monkeypatch):
    later = accounts._now() + timedelta(days=2)
    monkeypatch.setattr(accounts, "_now", lambda: later)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert "piclog_session=" in resp.headers.get("set-cookie", "")


def test_no_cookie_rewrite_when_fresh(client):
    assert "set-cookie" not in client.get("/api/auth/me").headers


def test_lockout_after_five_failures(anon_client):
    for _ in range(ratelimit.MAX_FAILURES):
        assert login(anon_client, password="wrong-password").status_code == 401
    resp = login(anon_client)  # 正确密码也不行
    assert resp.status_code == 429


def test_lockout_expires(anon_client, monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(ratelimit, "_clock", lambda: t[0])
    for _ in range(ratelimit.MAX_FAILURES):
        login(anon_client, password="wrong-password")
    assert login(anon_client).status_code == 429
    t[0] += ratelimit.LOCK_SECONDS + 1
    assert login(anon_client).status_code == 200


def test_success_resets_failure_count(anon_client):
    for _ in range(ratelimit.MAX_FAILURES - 1):
        login(anon_client, password="wrong-password")
    assert login(anon_client).status_code == 200
    for _ in range(ratelimit.MAX_FAILURES - 1):
        login(anon_client, password="wrong-password")
    assert login(anon_client).status_code == 200


def test_lockout_is_per_username(anon_client, make_user):
    """所有人可能同一个出口 IP：一个用户名被锁，不能连累别人。"""
    make_user("second")
    for _ in range(ratelimit.MAX_FAILURES):
        login(anon_client, password="wrong-password")
    assert login(anon_client).status_code == 429
    assert login(anon_client, "second", "password-2").status_code == 200


def test_new_user_can_log_in_and_use_app(make_user):
    c = make_user("second")
    assert c.get("/api/auth/me").json() == {"username": "second"}
    assert c.post("/api/categories", json={"name": "x"}).status_code == 201
```

Run: `cd backend && .venv/bin/pytest tests/test_auth.py -q`
Expected: FAIL（`anon_client` fixture 不存在 / `ratelimit` 模块不存在）

- [ ] **Step 2: 实现 `backend/ratelimit.py`**

```python
"""登录失败计数：连续失败 MAX_FAILURES 次后锁 LOCK_SECONDS 秒。

只放进程内存：重启即清零。单进程部署，够用。
"""
import threading
import time

MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60

_clock = time.monotonic
_lock = threading.Lock()
# key -> [连续失败次数, 锁定截止时刻]
_state: dict[tuple, list] = {}


def allowed(key: tuple) -> bool:
    with _lock:
        entry = _state.get(key)
        if not entry or entry[1] == 0:
            return True
        if _clock() >= entry[1]:
            del _state[key]
            return True
        return False


def record_failure(key: tuple):
    with _lock:
        entry = _state.setdefault(key, [0, 0])
        entry[0] += 1
        if entry[0] >= MAX_FAILURES:
            entry[1] = _clock() + LOCK_SECONDS


def record_success(key: tuple):
    with _lock:
        _state.pop(key, None)


def reset():
    with _lock:
        _state.clear()
```

- [ ] **Step 3: `models.py` 末尾追加**

```python
class LoginIn(BaseModel):
    username: str
    password: str


class MeOut(BaseModel):
    username: str
```

- [ ] **Step 4: 替换 `deps.py` 的临时 `current_user_id`**

在 import 区加 `from fastapi import Request, Response` 与 `import accounts`，并把临时的 `current_user_id` 替换成：

```python
SESSION_COOKIE = "piclog_session"


def set_session_cookie(response: Response, token: str):
    # NAS 走 http，不能设 Secure，否则浏览器不回传
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=int(accounts.SESSION_TTL.total_seconds()),
        httponly=True, samesite="lax", path="/",
    )


def clear_session_cookie(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def current_user(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE, "")
    conn = accounts.connect()
    try:
        result = accounts.resolve_session(conn, token)
    finally:
        conn.close()
    if result is None:
        raise HTTPException(401, "未登录")
    user, renewed = result
    if renewed:
        # 滑动续期：浏览器那边的 Max-Age 也要一起往后推
        set_session_cookie(response, token)
    return user


def current_user_id(user=Depends(current_user)) -> int:
    return user["id"]
```

- [ ] **Step 5: 实现 `backend/routers/auth.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Request, Response

import accounts
import ratelimit
from deps import clear_session_cookie, client_ip, current_user, set_session_cookie, SESSION_COOKIE
from models import LoginIn, MeOut

router = APIRouter(tags=["auth"])

BAD_CREDENTIALS = "账号或密码错误"


@router.get("/api/health")
def health():
    return {"status": "ok"}


@router.post("/api/auth/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response):
    # 按 (IP, 用户名) 计数：Docker 端口映射下所有人可能是同一个 IP
    key = ("user", client_ip(request), body.username)
    if not ratelimit.allowed(key):
        raise HTTPException(429, "尝试次数过多，请 15 分钟后再试")
    conn = accounts.connect()
    try:
        user = accounts.authenticate(conn, body.username, body.password)
        if user is None:
            ratelimit.record_failure(key)
            raise HTTPException(401, BAD_CREDENTIALS)
        ratelimit.record_success(key)
        accounts.purge_expired_sessions(conn)
        token = accounts.create_session(conn, user["id"])
    finally:
        conn.close()
    set_session_cookie(response, token)
    return {"username": user["username"]}


@router.post("/api/auth/logout", status_code=204)
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        conn = accounts.connect()
        try:
            accounts.delete_session(conn, token)
        finally:
            conn.close()
    clear_session_cookie(response)


@router.get("/api/auth/me", response_model=MeOut)
def me(user=Depends(current_user)):
    return {"username": user["username"]}
```

> `logout` 返回 204 时 FastAPI 仍会带上 `response` 上设置的 Set-Cookie。若实测发现清除 Cookie 的头丢失，改为 `return Response(status_code=204, headers=...)` 并用 `resp.delete_cookie(...)`。

- [ ] **Step 6: `main.py` 挂载 auth 路由**

`from routers import categories, logs, images, fields, search, files, auth`，并在其他 `include_router` 之前加 `app.include_router(auth.router)`。

- [ ] **Step 7: 改 `tests/conftest.py`**

在 import 区加 `import accounts`、`import ratelimit`；定义常量并改写 fixture：

```python
TEST_PASSWORD = "test-password-1"
os.environ["INITIAL_USER_PASSWORD"] = TEST_PASSWORD   # 替换 Step 6(Task 3) 里的那行


def _login(c, username, password):
    resp = c.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text


@pytest.fixture()
def anon_client():
    _reset_storage()
    ratelimit.reset()
    # TestClient 进入上下文时会触发 startup，startup 里会跑 bootstrap
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client(anon_client):
    _login(anon_client, "babelingz", TEST_PASSWORD)
    return anon_client


@pytest.fixture()
def make_user(anon_client):
    """再建一个账号，返回已登录的独立客户端（各自的 Cookie 互不干扰）。"""
    def _make(username, password="password-2"):
        conn = accounts.connect()
        uid = accounts.create_user(conn, username, password)
        conn.close()
        storage.provision_user(uid)
        # 不用 with：不重复触发 startup
        c = TestClient(app)
        _login(c, username, password)
        return c
    return _make
```

> 注意 `client` 和 `anon_client` 在同一个测试里同时使用时是**同一个对象**（`client` 就是登录后的 `anon_client`）。需要「一个登录、一个未登录」的测试请自己 `TestClient(app)` 新建未登录客户端。

- [ ] **Step 8: 给 `tests/test_files.py` 补未登录测试**

```python
def test_files_require_login(client):
    from fastapi.testclient import TestClient
    from main import app
    name = _log_with_image(client)
    assert TestClient(app).get(f"/api/files/{name}").status_code == 401
```

- [ ] **Step 9: 跑全量**

Run: `cd backend && .venv/bin/pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 10: Commit**

```bash
git add backend
git commit -m "Require login and resolve the user from a session cookie"
```

---

### Task 5: 跨账号隔离验收测试

**Files:**
- Test: `backend/tests/test_isolation.py`

**Interfaces:**
- Consumes: conftest 的 `client`、`make_user`、`fake_embedder`；`indexer.process_pending`
- Produces: 无（纯验收）。若有测试失败，修复点一定在 `deps.py` 或某个路由绕过了 `get_db` / `get_upload_dir`。

- [ ] **Step 1: 写测试**

```python
import pytest

import indexer
from tests.helpers import RED, solid_image_bytes


@pytest.fixture(autouse=True)
def clean_indexer_state():
    indexer.reset_state()
    yield
    indexer.reset_state()


@pytest.fixture()
def alice_data(client):
    """1 号账号的一套数据：分类、select 字段与选项、带图日志。"""
    cid = client.post("/api/categories", json={"name": "手套"}).json()["id"]
    field = client.post(
        f"/api/categories/{cid}/fields", json={"name": "颜色", "type": "select"}
    ).json()
    option = client.post(f"/api/fields/{field['id']}/options", json={"label": "红"}).json()
    log = client.post(
        "/api/logs",
        data={"category_id": cid, "description": "alice 的手套"},
        files=[("files", ("a.png", solid_image_bytes(RED), "image/png"))],
    ).json()
    return {"cid": cid, "fid": field["id"], "oid": option["id"], "log": log, "image": log["images"][0]}


def test_other_user_sees_empty_lists(alice_data, make_user):
    bob = make_user("bob")
    assert bob.get("/api/categories").json() == []
    assert bob.get("/api/logs").json()["total"] == 0


def test_other_user_cannot_read_or_change_by_id(alice_data, make_user):
    bob = make_user("bob")
    lid, cid, fid, oid = alice_data["log"]["id"], alice_data["cid"], alice_data["fid"], alice_data["oid"]
    iid, fname = alice_data["image"]["id"], alice_data["image"]["filename"]
    checks = [
        bob.get(f"/api/logs/{lid}"),
        bob.put(f"/api/logs/{lid}", json={"description": "hacked"}),
        bob.patch(f"/api/logs/{lid}/status", json={"status": "completed"}),
        bob.delete(f"/api/logs/{lid}"),
        bob.put(f"/api/categories/{cid}", json={"name": "hacked"}),
        bob.delete(f"/api/categories/{cid}"),
        bob.get(f"/api/categories/{cid}/fields"),
        bob.put(f"/api/fields/{fid}", json={"name": "hacked"}),
        bob.delete(f"/api/fields/{fid}"),
        bob.put(f"/api/options/{oid}", json={"label": "hacked"}),
        bob.delete(f"/api/options/{oid}"),
        bob.delete(f"/api/images/{iid}"),
        bob.get(f"/api/files/{fname}"),
        bob.get(f"/api/files/thumbs/{fname}"),
    ]
    for resp in checks:
        # 列字段接口对不存在的分类可能返回 []，其余一律 404；关键是不能是 2xx 且带了 alice 的数据
        assert resp.status_code in (404, 400) or resp.json() == [], (resp.request.url, resp.status_code, resp.text)


def test_alice_data_untouched_after_bob_attempts(client, alice_data, make_user):
    test_other_user_cannot_read_or_change_by_id(alice_data, make_user)
    log = client.get(f"/api/logs/{alice_data['log']['id']}").json()
    assert log["description"] == "alice 的手套"
    assert log["status"] == "pending"
    assert len(log["images"]) == 1
    assert client.get(f"/api/files/{alice_data['image']['filename']}").status_code == 200


def test_bob_cannot_upload_into_alice_log(alice_data, make_user):
    bob = make_user("bob")
    resp = bob.post(
        f"/api/logs/{alice_data['log']['id']}/images",
        files=[("files", ("x.png", solid_image_bytes(RED), "image/png"))],
    )
    assert resp.status_code == 404


def test_same_ids_in_both_accounts_stay_separate(client, make_user):
    """两个库的自增 id 都从 1 开始：同一个 id 在各自账号里指向各自的数据。"""
    bob = make_user("bob")
    a = client.post("/api/categories", json={"name": "alice-cat"}).json()
    b = bob.post("/api/categories", json={"name": "bob-cat"}).json()
    assert a["id"] == b["id"] == 1
    assert [c["name"] for c in client.get("/api/categories").json()] == ["alice-cat"]
    assert [c["name"] for c in bob.get("/api/categories").json()] == ["bob-cat"]


def test_image_search_only_returns_own_logs(client, fake_embedder, alice_data, make_user):
    bob = make_user("bob")
    indexer.process_pending()
    resp = bob.post(
        "/api/search/image",
        files={"file": ("q.png", solid_image_bytes(RED), "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["indexed"] == 0

    mine = client.post(
        "/api/search/image",
        files={"file": ("q.png", solid_image_bytes(RED), "image/png")},
    ).json()
    assert [h["log"]["id"] for h in mine["items"]] == [alice_data["log"]["id"]]
```

- [ ] **Step 2: 运行**

Run: `cd backend && .venv/bin/pytest tests/test_isolation.py -q`
Expected: PASS。若 `get /api/categories/{cid}/fields` 对不存在的分类返回 200 `[]`，断言已兼容；其余任何 2xx 都说明隔离有漏洞，必须修复路由而不是放宽断言。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_isolation.py
git commit -m "Add cross-account isolation tests"
```

---

### Task 6: 管理后台（接口 + 页面）

**Files:**
- Create: `backend/admin.py`
- Create: `backend/admin_page/index.html`
- Modify: `backend/main.py`（`create_app()`；按配置挂后台路由）
- Modify: `backend/tests/conftest.py`（设置 `ADMIN_PATH`、`ADMIN_PASSWORD`）
- Test: `backend/tests/test_admin.py`

> 注意：`backend/admin.py` 与目录 `backend/admin/` 同名。Python 中目录没有 `__init__.py` 且同级有 `admin.py` 时，`import admin` 解析为 `admin.py`（普通模块优先于命名空间包）。为避免歧义，**页面目录命名为 `backend/admin_page/`**，下文均用此名。

**Interfaces:**
- Consumes: `accounts.*`、`storage.provision_user/user_db_path`、`ratelimit.*`、`deps.client_ip`
- Produces:
  - `admin.ADMIN_COOKIE = "piclog_admin"`、`admin.configured_path() -> str | None`、`admin.build_router(path: str) -> APIRouter`
  - `main.create_app() -> FastAPI`；`main.app = create_app()`
  - 路由（前缀 `/<path>`）：`GET ""` → 307 到 `/<path>/`；`GET /` → 页面；`POST /api/login`；`POST /api/logout`；`GET /api/users`；`POST /api/users`；`PUT /api/users/{id}/password`；`PUT /api/users/{id}/active`

- [ ] **Step 1: conftest 加后台配置**

在 conftest 环境变量段，把 Task 3 加的两行 `os.environ.pop("ADMIN_...")` 换成：

```python
TEST_ADMIN_PATH = "console-testtesttesttest"
TEST_ADMIN_PASSWORD = "admin-password-1"
os.environ["ADMIN_PATH"] = TEST_ADMIN_PATH
os.environ["ADMIN_PASSWORD"] = TEST_ADMIN_PASSWORD
```

- [ ] **Step 2: 写失败的测试 `backend/tests/test_admin.py`**

```python
import sqlite3

import pytest
from fastapi.testclient import TestClient

import accounts
import ratelimit
import storage
from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_PATH, TEST_PASSWORD

P = f"/{TEST_ADMIN_PATH}"


# 管理员登录成功返回 204（无 body）
def admin_login(c, password=TEST_ADMIN_PASSWORD, username="admin"):
    return c.post(f"{P}/api/login", json={"username": username, "password": password})


@pytest.fixture()
def admin(anon_client):
    assert admin_login(anon_client).status_code == 204
    return anon_client


def test_page_is_served(anon_client):
    resp = anon_client.get(f"{P}/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "no-store" in resp.headers["cache-control"]


def test_path_without_slash_redirects(anon_client):
    resp = anon_client.get(P, follow_redirects=False)
    assert resp.status_code in (307, 308)
    assert resp.headers["location"].endswith(f"{P}/")


def test_admin_routes_hidden_from_openapi(anon_client):
    assert TEST_ADMIN_PATH not in anon_client.get("/openapi.json").text


def test_api_requires_admin_login(anon_client):
    assert anon_client.get(f"{P}/api/users").status_code == 401
    assert anon_client.post(f"{P}/api/users", json={"username": "x_user", "password": "password-1"}).status_code == 401


def test_user_session_is_not_admin(client):
    assert client.get(f"{P}/api/users").status_code == 401


@pytest.mark.parametrize("username,password", [
    ("admin", "wrong-password"),
    ("root", TEST_ADMIN_PASSWORD),
])
def test_bad_admin_login(anon_client, username, password):
    resp = admin_login(anon_client, password, username)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "账号或密码错误"


def test_admin_cookie_is_scoped_to_admin_path(anon_client):
    cookie = admin_login(anon_client).headers["set-cookie"]
    assert "piclog_admin=" in cookie
    assert f"Path={P}" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie or "SameSite=Strict" in cookie
    assert "Max-Age=43200" in cookie


def test_admin_lockout(anon_client):
    for _ in range(ratelimit.MAX_FAILURES):
        admin_login(anon_client, "wrong-password")
    assert admin_login(anon_client).status_code == 429


def test_admin_logout(admin):
    assert admin.post(f"{P}/api/logout").status_code == 204
    assert admin.get(f"{P}/api/users").status_code == 401


def test_list_users_with_counts(admin, client):
    # client 与 admin 是同一个 TestClient：它同时带着用户 Cookie 和管理员 Cookie
    cid = client.post("/api/categories", json={"name": "c"}).json()["id"]
    client.post("/api/logs", data={"category_id": cid},
                files=[("files", ("a.png", b"not-really-png", "image/png"))])
    lid = client.post("/api/logs", data={"category_id": cid}).json()["id"]
    client.delete(f"/api/logs/{lid}")  # 软删除的不计

    [row] = admin.get(f"{P}/api/users").json()
    assert row["id"] == 1 and row["username"] == "babelingz" and row["is_active"] is True
    assert row["log_count"] == 1 and row["image_count"] == 1
    assert "created_at" in row


def test_create_user_then_login(admin):
    resp = admin.post(f"{P}/api/users", json={"username": "carol", "password": "carol-pass-1"})
    assert resp.status_code == 201
    uid = resp.json()["id"]
    c = TestClient(admin.app)
    assert c.post("/api/auth/login", json={"username": "carol", "password": "carol-pass-1"}).status_code == 200
    assert c.get("/api/categories").json() == []
    assert storage.user_db_path(uid).endswith(f"users/{uid}/piclog.db")


def test_create_duplicate_is_409(admin):
    assert admin.post(f"{P}/api/users", json={"username": "babelingz", "password": "password-9"}).status_code == 409


@pytest.mark.parametrize("body", [
    {"username": "No", "password": "password-1"},
    {"username": "valid_name", "password": "short"},
])
def test_create_invalid_is_400(admin, body):
    assert admin.post(f"{P}/api/users", json=body).status_code == 400


def test_reset_password(admin):
    user_client = TestClient(admin.app)
    user_client.post("/api/auth/login", json={"username": "babelingz", "password": TEST_PASSWORD})
    assert admin.put(f"{P}/api/users/1/password", json={"password": "brand-new-1"}).status_code == 204
    assert user_client.get("/api/categories").status_code == 401
    assert user_client.post("/api/auth/login", json={"username": "babelingz", "password": "brand-new-1"}).status_code == 200


def test_deactivate_and_reactivate(admin):
    user_client = TestClient(admin.app)
    user_client.post("/api/auth/login", json={"username": "babelingz", "password": TEST_PASSWORD})
    assert admin.put(f"{P}/api/users/1/active", json={"is_active": False}).status_code == 204
    assert user_client.get("/api/categories").status_code == 401
    assert admin.get(f"{P}/api/users").json()[0]["is_active"] is False
    assert admin.put(f"{P}/api/users/1/active", json={"is_active": True}).status_code == 204
    assert user_client.post("/api/auth/login", json={"username": "babelingz", "password": TEST_PASSWORD}).status_code == 200


def test_unknown_user_is_404(admin):
    assert admin.put(f"{P}/api/users/99/password", json={"password": "password-9"}).status_code == 404
    assert admin.put(f"{P}/api/users/99/active", json={"is_active": False}).status_code == 404


def test_disabled_when_path_not_configured(monkeypatch):
    import main
    monkeypatch.delenv("ADMIN_PATH")
    app = main.create_app()
    with TestClient(app) as c:
        assert c.get(f"{P}/").status_code == 404
        assert c.post(f"{P}/api/login", json={"username": "admin", "password": TEST_ADMIN_PASSWORD}).status_code == 404


@pytest.mark.parametrize("bad", ["short", "has/slash-aaaaaaaaaaaa", "api"])
def test_invalid_admin_path_disables_admin(monkeypatch, bad):
    import admin as admin_module
    monkeypatch.setenv("ADMIN_PATH", bad)
    assert admin_module.configured_path() is None


def test_disabled_when_admin_password_never_set(anon_client):
    conn = accounts.connect()
    conn.execute("DELETE FROM admin")
    conn.commit()
    conn.close()
    assert anon_client.get(f"{P}/").status_code == 404
    assert admin_login(anon_client).status_code == 404
```

Run: `cd backend && .venv/bin/pytest tests/test_admin.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'admin'`）

- [ ] **Step 3: 实现 `backend/admin.py`**

```python
"""管理后台：挂在环境变量 ADMIN_PATH 指定的隐藏前缀下。

- 页面是 admin_page/index.html，不进前端打包，用户端代码里没有这个路径
- 路由全部 include_in_schema=False，不会出现在 /openapi.json 和 /docs
- 管理员密码还没写入库时，整个后台当作不存在（404）
"""
import logging
import os
import re
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

import accounts
import ratelimit
import storage
from deps import client_ip

log = logging.getLogger("piclog.admin")

ADMIN_COOKIE = "piclog_admin"
ADMIN_USERNAME = "admin"
ADMIN_PATH_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin_page", "index.html")
BAD_CREDENTIALS = "账号或密码错误"


class AdminLoginIn(BaseModel):
    username: str
    password: str


class NewUserIn(BaseModel):
    username: str
    password: str


class PasswordIn(BaseModel):
    password: str


class ActiveIn(BaseModel):
    is_active: bool


def configured_path() -> Optional[str]:
    raw = os.environ.get("ADMIN_PATH", "").strip().strip("/")
    if not raw:
        return None
    if not ADMIN_PATH_RE.match(raw):
        log.warning("ADMIN_PATH 格式不对（需 16–128 位字母、数字、- 或 _），管理后台未启用")
        return None
    return raw


def _enabled():
    conn = accounts.connect()
    try:
        if not accounts.admin_configured(conn):
            raise HTTPException(404, "Not Found")
    finally:
        conn.close()


def _require_admin(request: Request):
    conn = accounts.connect()
    try:
        ok = accounts.check_admin_session(conn, request.cookies.get(ADMIN_COOKIE, ""))
    finally:
        conn.close()
    if not ok:
        raise HTTPException(401, "未登录")


def _counts(uid: int) -> tuple[Optional[int], Optional[int]]:
    """只读打开该用户的库数一下；打不开就给 None，不影响列表其余部分。"""
    path = storage.user_db_path(uid)
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            logs = conn.execute("SELECT COUNT(*) FROM logs WHERE deleted_at IS NULL").fetchone()[0]
            images = conn.execute(
                "SELECT COUNT(*) FROM images i JOIN logs l ON l.id = i.log_id "
                "WHERE l.deleted_at IS NULL"
            ).fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        log.exception("读取用户 %s 的统计失败", uid)
        return None, None
    return logs, images


def build_router(path: str) -> APIRouter:
    prefix = f"/{path}"
    router = APIRouter(prefix=prefix, include_in_schema=False, dependencies=[Depends(_enabled)])

    @router.get("")
    def to_slash():
        # 页面里的接口地址是相对路径 api/...，必须以斜杠结尾访问
        return RedirectResponse(f"{prefix}/")

    @router.get("/")
    def page():
        return FileResponse(PAGE, headers={"Cache-Control": "no-store"})

    @router.post("/api/login", status_code=204)
    def login(body: AdminLoginIn, request: Request, response: Response):
        key = ("admin", client_ip(request))
        if not ratelimit.allowed(key):
            raise HTTPException(429, "尝试次数过多，请 15 分钟后再试")
        conn = accounts.connect()
        try:
            ok = accounts.verify_admin(conn, body.password) and body.username == ADMIN_USERNAME
            if not ok:
                ratelimit.record_failure(key)
                raise HTTPException(401, BAD_CREDENTIALS)
            ratelimit.record_success(key)
            accounts.purge_expired_sessions(conn)
            token = accounts.create_admin_session(conn)
        finally:
            conn.close()
        response.set_cookie(
            ADMIN_COOKIE, token,
            max_age=int(accounts.ADMIN_SESSION_TTL.total_seconds()),
            httponly=True, samesite="strict", path=prefix,
        )

    @router.post("/api/logout", status_code=204)
    def logout(request: Request, response: Response):
        token = request.cookies.get(ADMIN_COOKIE)
        if token:
            conn = accounts.connect()
            try:
                accounts.delete_admin_session(conn, token)
            finally:
                conn.close()
        response.delete_cookie(ADMIN_COOKIE, path=prefix)

    @router.get("/api/users", dependencies=[Depends(_require_admin)])
    def list_users():
        conn = accounts.connect()
        try:
            rows = accounts.list_users(conn)
        finally:
            conn.close()
        result = []
        for r in rows:
            log_count, image_count = _counts(r["id"])
            result.append({
                "id": r["id"], "username": r["username"], "is_active": bool(r["is_active"]),
                "created_at": r["created_at"], "log_count": log_count, "image_count": image_count,
            })
        return result

    @router.post("/api/users", status_code=201, dependencies=[Depends(_require_admin)])
    def create_user(body: NewUserIn):
        conn = accounts.connect()
        try:
            uid = accounts.create_user(conn, body.username, body.password)
        except accounts.UsernameTaken:
            raise HTTPException(409, "用户名已存在")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        finally:
            conn.close()
        storage.provision_user(uid)
        return {"id": uid, "username": body.username}

    def _existing(conn, uid: int):
        if accounts.get_user(conn, uid) is None:
            raise HTTPException(404, "用户不存在")

    @router.put("/api/users/{uid}/password", status_code=204, dependencies=[Depends(_require_admin)])
    def reset_password(uid: int, body: PasswordIn):
        conn = accounts.connect()
        try:
            _existing(conn, uid)
            accounts.set_password(conn, uid, body.password)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        finally:
            conn.close()

    @router.put("/api/users/{uid}/active", status_code=204, dependencies=[Depends(_require_admin)])
    def set_active(uid: int, body: ActiveIn):
        conn = accounts.connect()
        try:
            _existing(conn, uid)
            accounts.set_active(conn, uid, body.is_active)
        finally:
            conn.close()

    return router
```


- [ ] **Step 4: `main.py` 改为工厂函数**

```python
import logging
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import admin
import bootstrap
import indexer
from routers import auth, categories, logs, images, fields, search, files

STATIC_DIR = os.environ.get("STATIC_DIR", "/app/static")
log = logging.getLogger("piclog")


def create_app() -> FastAPI:
    app = FastAPI(title="PicLog")

    app.include_router(auth.router)
    app.include_router(categories.router)
    app.include_router(logs.router)
    app.include_router(images.router)
    app.include_router(fields.router)
    app.include_router(search.router)
    app.include_router(files.router)

    # 必须在 SPA 兜底路由之前注册
    admin_path = admin.configured_path()
    if admin_path:
        app.include_router(admin.build_router(admin_path))
    else:
        log.warning("未配置 ADMIN_PATH，管理后台未启用")

    @app.on_event("startup")
    def startup():
        bootstrap.run()
        indexer.start()

    if os.path.isdir(STATIC_DIR):
        app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = os.path.join(STATIC_DIR, full_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    return app


app = create_app()
```

- [ ] **Step 5: 写管理后台页面 `backend/admin_page/index.html`**

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>PicLog 账号管理</title>
<style>
  :root { --bg:#f8fafc; --card:#fff; --line:#e2e8f0; --text:#0f172a; --muted:#64748b;
          --primary:#4f46e5; --primary-hover:#4338ca; --danger:#dc2626; --ok:#16a34a; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:14px/1.5 -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", sans-serif; }
  main { max-width:720px; margin:0 auto; padding:24px 16px 48px; }
  h1 { font-size:20px; margin:0 0 16px; display:flex; align-items:center; justify-content:space-between; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:16px; margin-bottom:16px;
          box-shadow:0 1px 2px rgba(15,23,42,.04); }
  .card h2 { font-size:15px; margin:0 0 12px; }
  input { width:100%; padding:9px 12px; border:1px solid var(--line); border-radius:10px; font:inherit; }
  input:focus { outline:none; border-color:var(--primary); box-shadow:0 0 0 3px #e0e7ff; }
  button { padding:8px 14px; border:0; border-radius:10px; font:inherit; font-weight:500; cursor:pointer;
           background:var(--primary); color:#fff; white-space:nowrap; }
  button:hover { background:var(--primary-hover); }
  button.ghost { background:transparent; color:var(--muted); border:1px solid var(--line); }
  button.ghost:hover { background:#f1f5f9; }
  button.danger { background:transparent; color:var(--danger); border:1px solid #fecaca; }
  button:disabled { opacity:.5; cursor:default; }
  .row { display:flex; gap:8px; align-items:center; }
  .row > input { flex:1; min-width:0; }
  .stack > * + * { margin-top:10px; }
  .msg { font-size:13px; margin-top:8px; min-height:1.5em; }
  .msg.err { color:var(--danger); }
  .msg.ok { color:var(--ok); }
  .user { display:flex; flex-wrap:wrap; gap:8px 12px; align-items:center; padding:12px 0; border-top:1px solid var(--line); }
  .user:first-child { border-top:0; padding-top:0; }
  .user .name { font-weight:600; }
  .user .meta { color:var(--muted); font-size:12px; flex-basis:100%; }
  .user .actions { margin-left:auto; display:flex; gap:6px; }
  .badge { font-size:12px; padding:1px 8px; border-radius:999px; background:#dcfce7; color:#166534; }
  .badge.off { background:#f1f5f9; color:var(--muted); }
  .hidden { display:none; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0f172a; --card:#1e293b; --line:#334155; --text:#e2e8f0; --muted:#94a3b8; }
    input { background:#0f172a; color:var(--text); }
    button.ghost:hover { background:#334155; }
    .badge { background:#14532d; color:#bbf7d0; }
    .badge.off { background:#334155; }
  }
</style>
</head>
<body>
<main>
  <section id="login-view" class="hidden">
    <h1>PicLog 账号管理</h1>
    <form id="login-form" class="card stack">
      <input name="username" placeholder="管理员账号" autocomplete="username" required>
      <input name="password" type="password" placeholder="密码" autocomplete="current-password" required>
      <button type="submit">登录</button>
      <div class="msg err" id="login-msg"></div>
    </form>
  </section>

  <section id="app-view" class="hidden">
    <h1>账号管理 <button class="ghost" id="logout">退出</button></h1>

    <form id="create-form" class="card stack">
      <h2>新建账号</h2>
      <input name="username" placeholder="用户名（3–32 位小写字母、数字、下划线）" autocomplete="off" required>
      <div class="row">
        <input name="password" placeholder="初始密码（至少 8 位）" autocomplete="new-password" required>
        <button type="button" class="ghost" id="gen">随机生成</button>
      </div>
      <button type="submit">创建</button>
      <div class="msg" id="create-msg"></div>
    </form>

    <div class="card">
      <h2>全部账号</h2>
      <div id="users"></div>
    </div>
  </section>
</main>

<script>
// 接口用相对路径：页面总是以 /<后台路径>/ 访问，这里不写死路径
async function call(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401 && !url.endsWith('login')) { show('login'); throw new Error('请重新登录') }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const d = data.detail
    throw new Error(typeof d === 'string' ? d : Array.isArray(d) ? d.map(x => x.msg).join('；') : `请求失败（${res.status}）`)
  }
  return res.status === 204 ? null : res.json()
}

const $ = (id) => document.getElementById(id)

function show(view) {
  $('login-view').classList.toggle('hidden', view !== 'login')
  $('app-view').classList.toggle('hidden', view !== 'app')
}

function setMsg(el, text, kind) {
  el.textContent = text
  el.className = 'msg' + (kind ? ' ' + kind : '')
}

function randomPassword() {
  // 去掉易混淆的 0/O、1/l/I
  const chars = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  const buf = new Uint32Array(14)
  crypto.getRandomValues(buf)
  return Array.from(buf, (n) => chars[n % chars.length]).join('')
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
}

async function loadUsers() {
  const users = await call('GET', 'api/users')
  $('users').innerHTML = users.map((u) => `
    <div class="user" data-id="${u.id}">
      <span class="name">${esc(u.username)}</span>
      <span class="badge ${u.is_active ? '' : 'off'}">${u.is_active ? '启用' : '已停用'}</span>
      <span class="actions">
        <button class="ghost" data-act="reset">重置密码</button>
        <button class="${u.is_active ? 'danger' : 'ghost'}" data-act="toggle" data-active="${u.is_active}">
          ${u.is_active ? '停用' : '启用'}
        </button>
      </span>
      <span class="meta">
        创建于 ${esc(u.created_at)} · 日志 ${u.log_count ?? '?'} 条 · 图片 ${u.image_count ?? '?'} 张
      </span>
    </div>`).join('')
}

$('users').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-act]')
  if (!btn) return
  const row = btn.closest('.user')
  const id = row.dataset.id
  const name = row.querySelector('.name').textContent
  try {
    if (btn.dataset.act === 'reset') {
      const pw = window.prompt(`为 ${name} 设置新密码（至少 8 位）。留空则随机生成：`, '')
      if (pw === null) return
      const password = pw || randomPassword()
      await call('PUT', `api/users/${id}/password`, { password })
      window.alert(`${name} 的新密码：\n\n${password}\n\n该账号已登录的设备都需要重新登录。`)
    } else {
      const active = btn.dataset.active === 'true'
      if (active && !window.confirm(`停用 ${name}？停用后无法登录，数据会保留。`)) return
      await call('PUT', `api/users/${id}/active`, { is_active: !active })
    }
    await loadUsers()
  } catch (err) {
    window.alert(err.message)
  }
})

$('login-form').addEventListener('submit', async (e) => {
  e.preventDefault()
  const f = e.target
  try {
    await call('POST', 'api/login', { username: f.username.value.trim(), password: f.password.value })
    f.reset()
    setMsg($('login-msg'), '')
    show('app')
    await loadUsers()
  } catch (err) {
    setMsg($('login-msg'), err.message, 'err')
  }
})

$('gen').addEventListener('click', () => {
  $('create-form').password.value = randomPassword()
})

$('create-form').addEventListener('submit', async (e) => {
  e.preventDefault()
  const f = e.target
  const username = f.username.value.trim()
  const password = f.password.value
  try {
    await call('POST', 'api/users', { username, password })
    f.reset()
    setMsg($('create-msg'), `已创建 ${username}，初始密码：${password}`, 'ok')
    await loadUsers()
  } catch (err) {
    setMsg($('create-msg'), err.message, 'err')
  }
})

$('logout').addEventListener('click', async () => {
  await call('POST', 'api/logout').catch(() => {})
  show('login')
})

// 首次打开：能拿到列表说明已登录
loadUsers().then(() => show('app')).catch(() => show('login'))
</script>
</body>
</html>
```

> 页面里的 `window.prompt/alert/confirm` 是管理员自用的简单交互，可接受。

- [ ] **Step 6: 确认 Docker 镜像会带上页面**

`Dockerfile` 已有 `COPY backend/ .`，`admin_page/` 会随之进入镜像；`.dockerignore` 只排除了 `backend/tests` 和 `backend/.venv`，无需改动。

Run: `grep -n "admin_page\|backend/" .dockerignore`
Expected: 没有排除 `admin_page` 的规则

- [ ] **Step 7: 运行**

Run: `cd backend && .venv/bin/pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 8: 本地手工看一眼页面**

```bash
cd backend && DB_PATH=./devdata/piclog.db UPLOAD_DIR=./devuploads \
  INITIAL_USER_PASSWORD=devpassword1 ADMIN_PATH=dev-admin-console-000001 ADMIN_PASSWORD=devadminpass1 \
  .venv/bin/python -m uvicorn main:app --port 8080
```

浏览器打开 `http://localhost:8080/dev-admin-console-000001/`：用 admin / devadminpass1 登录；新建账号、随机生成密码、重置密码、停用/启用各点一遍；手机宽度（375px）下布局不溢出。注意：本地已有的 `devdata/piclog.db` 会被迁移到 `devdata/users/1/`，这是预期行为。

- [ ] **Step 9: Commit**

```bash
git add backend/admin.py backend/admin_page backend/main.py backend/tests
git commit -m "Add hidden admin console for managing accounts"
```

---

### Task 7: 前端登录

**Files:**
- Create: `frontend/src/auth.js`
- Create: `frontend/src/views/Login.vue`
- Modify: `frontend/src/api.js`、`frontend/src/router.js`、`frontend/src/App.vue`、`frontend/src/components/TopBar.vue`、`frontend/src/views/Categories.vue`、`frontend/src/thumbs.js`、`frontend/src/views/LogDetail.vue`、`frontend/vite.config.js`

**Interfaces:**
- Consumes: `/api/auth/login|logout|me`、`/api/files/...`
- Produces:
  - `auth.js`：`currentUser`（`ref<string|null>`）、`ensureSession(): Promise<string|null>`、`setUser(username)`、`logout(): Promise<void>`（整页跳 `/login`）
  - `api.login(username, password)`
  - 路由 `/login`（`meta.public = true`）

- [ ] **Step 1: `frontend/src/auth.js`**

```js
import { ref } from 'vue'

// 当前登录的用户名；null = 未登录。首次导航时向后端问一次，之后靠 401 兜底
export const currentUser = ref(null)
let checked = false

export async function ensureSession() {
  if (checked) return currentUser.value
  try {
    const res = await fetch('/api/auth/me')
    currentUser.value = res.ok ? (await res.json()).username : null
  } catch {
    currentUser.value = null
  }
  checked = true
  return currentUser.value
}

export function setUser(username) {
  currentUser.value = username
  checked = true
}

export async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' }).catch(() => {})
  // 整页跳转而不是 router.push：列表页被 keep-alive 缓存着上一个账号的数据，
  // 必须整个丢掉，下一个人登录后才不会先看到别人的列表
  window.location.assign('/login')
}
```

- [ ] **Step 2: `api.js` 处理 401 并加 `login`**

把 `request` 改为：

```js
async function request(url, options = {}) {
  const { noAuthRedirect, ...fetchOptions } = options
  const res = await fetch(BASE + url, fetchOptions)
  if (res.status === 401 && !noAuthRedirect) {
    // 会话过期、被停用或改了密码：回登录页，登录后回到原来的页面。
    // 整页跳转，理由同 auth.js 的 logout
    const back = window.location.pathname + window.location.search
    window.location.assign(`/login?redirect=${encodeURIComponent(back)}`)
    throw Object.assign(new Error('请重新登录'), { status: 401 })
  }
  if (res.status === 204) return null
  // 以下与原来相同
  ...
}
```

在 `export const api = {` 的开头加：

```js
  // Auth
  login: (username, password) => request('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    // 登录失败的 401 只是「密码错」，留在登录页显示
    noAuthRedirect: true,
  }),
```

- [ ] **Step 3: `views/Login.vue`**

```vue
<template>
  <div class="flex min-h-[80vh] items-center justify-center">
    <form
      @submit.prevent="submit"
      class="w-full max-w-sm space-y-4 rounded-2xl border border-slate-100 bg-white p-6 shadow-sm"
    >
      <h1 class="text-center text-xl font-bold text-primary-600">PicLog</h1>
      <input
        v-model.trim="username"
        placeholder="账号"
        autocomplete="username"
        autocapitalize="none"
        required
        class="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
      />
      <input
        v-model="password"
        type="password"
        placeholder="密码"
        autocomplete="current-password"
        required
        class="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
      />
      <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
      <button
        type="submit"
        :disabled="busy"
        class="w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-primary-700 disabled:opacity-60"
      >
        {{ busy ? '登录中…' : '登录' }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'
import { setUser } from '../auth.js'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

// 只接受站内路径，防止 ?redirect=//evil.com 这类开放跳转
function safeRedirect(value) {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') ? value : '/'
}

async function submit() {
  error.value = ''
  busy.value = true
  try {
    const me = await api.login(username.value, password.value)
    setUser(me.username)
    router.replace(safeRedirect(route.query.redirect))
  } catch (e) {
    error.value = e.message
    password.value = ''
  } finally {
    busy.value = false
  }
}
</script>
```

- [ ] **Step 4: `router.js` 加登录路由与守卫**

import 区加：

```js
import Login from './views/Login.vue'
import { ensureSession } from './auth.js'
```

`routes` 数组最前面加：

```js
  { path: '/login', name: 'Login', component: Login, meta: { public: true } },
```

把 `export default createRouter({...})` 改成 `const router = createRouter({...})`，末尾追加：

```js
router.beforeEach(async (to) => {
  const user = await ensureSession()
  if (to.meta.public) return user ? { path: '/' } : true
  if (!user) return { name: 'Login', query: { redirect: to.fullPath } }
  return true
})

export default router
```

- [ ] **Step 5: `App.vue` 登录页不显示导航**

```vue
<template>
  <div class="min-h-screen bg-slate-50">
    <TopBar v-if="!route.meta.public" />
    <main class="mx-auto max-w-2xl px-4 pb-24 pt-6 md:pb-8">
      <!-- 缓存列表页和搜图结果页：从详情卡片进编辑页再回来，筛选、已加载页数、滚动位置都保留 -->
      <router-view v-slot="{ Component }">
        <keep-alive :include="['LogList', 'ImageSearch']">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
    <BottomNav v-if="!route.meta.public" />
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'
import TopBar from './components/TopBar.vue'
import BottomNav from './components/BottomNav.vue'

const route = useRoute()
</script>
```

- [ ] **Step 6: 桌面顶栏显示用户名与退出**

`TopBar.vue` 中，在「新建」`router-link` 之后、`</nav>` 之前加：

```vue
        <span class="ml-3 text-sm text-slate-400">{{ currentUser }}</span>
        <button
          @click="logout"
          class="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
        >
          退出
        </button>
```

文件末尾加：

```vue
<script setup>
import { currentUser, logout } from '../auth.js'
</script>
```

- [ ] **Step 7: 手机端在分类页底部放退出入口**

手机上没有顶栏（`TopBar` 是 `hidden md:block`），底部导航也没有空位。`Categories.vue` 模板最外层 `<div>` 的结束标签（第 105 行 `  </div>`，紧挨 `</template>`）之前插入：

```vue
    <div class="mt-8 flex items-center justify-between rounded-2xl border border-slate-100 bg-white px-4 py-3 text-sm shadow-sm md:hidden">
      <span class="text-slate-500">当前账号 <span class="font-medium text-slate-900">{{ currentUser }}</span></span>
      <button @click="logout" class="font-medium text-red-500">退出登录</button>
    </div>
```

`<script setup>` 的 import 区加 `import { currentUser, logout } from '../auth.js'`。

- [ ] **Step 8: 图片地址改走 `/api/files`**

`thumbs.js`：

```js
export function thumbUrl(filename) {
  return `/api/files/thumbs/${encodeURIComponent(filename)}?v=${THUMB_VERSION}`
}
```

`LogDetail.vue` 预览图：`:src="`/uploads/${previewImg.filename}`"` → `:src="`/api/files/${encodeURIComponent(previewImg.filename)}`"`

`vite.config.js`：删掉 `'/uploads': 'http://localhost:8080'` 这一行（及上一行末尾的逗号）。

Run: `grep -rn "/uploads" frontend/src frontend/vite.config.js`
Expected: 无输出

- [ ] **Step 9: 构建**

Run: `cd frontend && npm run build`
Expected: 构建成功，无报错

- [ ] **Step 10: 本地端到端手工验证**

后端按 Task 6 Step 8 的命令启动，另开终端 `cd frontend && npm run dev`，打开 Vite 地址：
1. 未登录访问 `/` → 跳到 `/login?redirect=%2F`
2. 错误密码 → 显示「账号或密码错误」，停留在登录页
3. `babelingz` / `devpassword1` 登录 → 回到列表，已有日志和缩略图正常显示；打开详情，点图片看原图
4. 在 `/logs/new` 刷新页面 → 仍在该页（会话有效）
5. 在管理后台停用 babelingz，回到应用点任意操作 → 跳到登录页，且 `redirect` 为当前页
6. 重新启用，在管理后台新建 `second`，用它登录 → 列表为空，分类为空；新建一条带图日志；以图搜图只搜到自己的
7. 退出后用 babelingz 登录 → 看不到 `second` 的日志
8. 浏览器宽度切到 375px：分类页底部有「当前账号 · 退出登录」，登录页不显示顶栏和底部导航

- [ ] **Step 11: Commit**

```bash
git add frontend
git commit -m "Add login page and route guard; load images through the files API"
```

---

### Task 8: 部署与脚本

**Files:**
- Create: `.env.example`
- Modify: `docker-compose.yml`、`.gitignore`、`.dockerignore`、`scripts/deploy.sh`、`scripts/setup-dev.sh`、`scripts/eval-search.py`

**Interfaces:**
- Consumes: `/api/health`、`/api/auth/login`
- Produces: NAS 上首次部署前自动备份；缺 `.env` 时部署中止

- [ ] **Step 1: `.env.example`**

```
# 复制为 .env，放在 NAS 部署目录（与 docker-compose.yml 同级）。不要提交到 git。
# 三个值都只在首次启动时写入数据库，之后修改这里不会改变已有密码。

# 管理后台路径：16–128 位字母、数字、- 或 _，例如 console-<32 位随机串>
ADMIN_PATH=
# 管理员（用户名 admin）的初始密码
ADMIN_PASSWORD=
# 首个账号 babelingz 的初始密码（至少 8 位）
INITIAL_USER_PASSWORD=
```

- [ ] **Step 2: `docker-compose.yml` 读 `.env`**

在 `restart: unless-stopped` 下一行加：

```yaml
    env_file:
      - .env
```

- [ ] **Step 3: `.gitignore` 与 `.dockerignore` 排除备份目录**

两个文件末尾各加一行 `backups/`。

- [ ] **Step 4: `deploy.sh`：健康检查路径、`.env` 检查、首次迁移前备份**

- `HEALTH_PATH="${PICLOG_HEALTH_PATH:-/api/categories}"` → `HEALTH_PATH="${PICLOG_HEALTH_PATH:-/api/health}"`
- 「重建容器」一节的 heredoc 替换为：

```bash
run_logged "容器重建" ssh "${SSH_OPTS[@]}" "$NAS_HOST" bash -s <<EOF
set -euo pipefail
# 非交互式 SSH 的 PATH 不含 /usr/local/bin，而 docker-compose v1 要在 PATH 上找 docker
export PATH="${REMOTE_PATH}:\$PATH"
cd '$NAS_DIR'
git reset --hard '${DEPLOY_REF#refs/heads/}'
if [ ! -f .env ]; then
    echo "缺少 $NAS_DIR/.env：参考仓库里的 .env.example 创建" >&2
    exit 1
fi
'$NAS_COMPOSE' build
if [ ! -f data/accounts.db ]; then
    # 即将第一次迁移到多账号布局：先停容器，保证库文件一致，再整份备份
    backup="backups/pre-multiuser-\$(date +%Y%m%d-%H%M%S)"
    '$NAS_COMPOSE' stop '$NAS_SERVICE'
    mkdir -p "\$backup"
    cp -a data uploads "\$backup/"
    echo "已备份到 $NAS_DIR/\$backup"
fi
'$NAS_COMPOSE' up -d
EOF
```

> `.env` 检查放在 `git reset` 之后：`.env` 是未跟踪文件，`reset --hard` 不会删它。

Run: `bash -n scripts/deploy.sh`
Expected: 无输出（语法正确）

- [ ] **Step 5: `setup-dev.sh` 的本地启动说明**

把「终端 1」那三行改为：

```
  终端 1  cd backend && DB_PATH=./devdata/piclog.db UPLOAD_DIR=./devuploads \
            MODEL_PATH=./devdata/models/dinov2-small.onnx \
            INITIAL_USER_PASSWORD=devpassword1 \
            ADMIN_PATH=dev-admin-console-000001 ADMIN_PASSWORD=devadminpass1 \
            .venv/bin/python -m uvicorn main:app --reload --port 8080
          应用：用 babelingz / devpassword1 登录
          后台：http://localhost:8080/dev-admin-console-000001/（admin / devadminpass1）
```

- [ ] **Step 6: `eval-search.py` 先登录**

docstring 用法行改为：

```
    PICLOG_USERNAME=babelingz PICLOG_PASSWORD=... \
    backend/.venv/bin/python scripts/eval-search.py <照片目录> [--url http://192.168.8.10:8080]
```

`main()` 中参数解析后加：

```python
    ap.add_argument("--username", default=os.environ.get("PICLOG_USERNAME", ""))
    ap.add_argument("--password", default=os.environ.get("PICLOG_PASSWORD", ""))
```

（放在 `args = ap.parse_args()` 之前），顶部加 `import os`。在 `with httpx.Client(timeout=120) as client:` 之后第一行加：

```python
        # 搜索只在登录账号自己的图片里进行
        login = client.post(f"{base}/api/auth/login", json={"username": args.username, "password": args.password})
        if login.status_code != 200:
            sys.exit(f"登录失败：{login.status_code} {login.text}（用 PICLOG_USERNAME / PICLOG_PASSWORD 提供账号）")
```

Run: `backend/.venv/bin/python -m py_compile scripts/eval-search.py`
Expected: 无输出

- [ ] **Step 7: 全量测试与构建**

Run: `cd backend && .venv/bin/pytest tests -q && cd ../frontend && npm run build`
Expected: 全部通过

- [ ] **Step 8: Commit**

```bash
git add .env.example docker-compose.yml .gitignore .dockerignore scripts
git commit -m "Deploy with an env file, back up before the first multi-user migration"
```

---

## 上线（实现全部完成后，与用户一起做，不属于任何任务）

1. 本地生成 `ADMIN_PATH`（`console-` + 32 位随机小写字母数字）与 `ADMIN_PASSWORD`（24 位随机），**只在对话里交给用户**，不写入仓库
2. 用户在 NAS 上创建 `/volume2/homes/darlingz/pic/.env`（三个变量，`INITIAL_USER_PASSWORD` 为用户指定的值）
3. `git push` → deploy.sh 跑测试、构建、检查 `.env`、首次备份、重建、健康检查
4. 手机上用 babelingz 登录，确认历史日志、图片、以图搜图都在；打开后台地址确认能登录
