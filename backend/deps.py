"""请求级依赖：当前是谁、他的库、他的上传目录。

所有业务路由都通过这里的 get_db / get_upload_dir 访问数据，
按账号隔离就收口在这一个文件里。
"""
import logging
import os

from fastapi import Depends, HTTPException, Request, Response

import accounts
import database
import storage

log = logging.getLogger("piclog.deps")


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
