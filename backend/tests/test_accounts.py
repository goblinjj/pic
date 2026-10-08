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


@pytest.mark.parametrize("username", ["a", "张", "张三\n", "Alice", "a-b", "张 三", "张三！", "a" * 33, ""])
def test_invalid_username_rejected(conn, username):
    with pytest.raises(ValueError):
        accounts.create_user(conn, username, "password-1")


@pytest.mark.parametrize("password", ["short", "x" * 129])
def test_invalid_password_rejected(conn, password):
    with pytest.raises(ValueError):
        accounts.create_user(conn, "alice", password)


@pytest.mark.parametrize("username", ["张三", "小王_2", "ab", "abc", "a" * 32])
def test_chinese_and_short_usernames_accepted(conn, username):
    uid = accounts.create_user(conn, username, "password-1")
    assert accounts.authenticate(conn, username, "password-1")["id"] == uid


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
