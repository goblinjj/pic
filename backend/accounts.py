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


def validate_password(password: str):
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
    validate_password(password)
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
    validate_password(password)
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
    ok = verify_password(password, row["password_hash"] if row else _DUMMY_HASH)
    return ok and row is not None


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
