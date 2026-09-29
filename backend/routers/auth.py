from fastapi import APIRouter, Depends, HTTPException, Request, Response

import accounts
import ratelimit
from deps import SESSION_COOKIE, clear_session_cookie, client_ip, current_user, set_session_cookie
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
