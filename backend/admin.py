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
