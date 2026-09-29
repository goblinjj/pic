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


# 先于 /{filename} 注册（{filename} 本就不匹配斜杠，顺序写清楚更稳）
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
