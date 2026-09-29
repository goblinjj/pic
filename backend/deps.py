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
