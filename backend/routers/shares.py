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
