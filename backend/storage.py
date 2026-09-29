"""数据目录布局。

    <DATA_DIR>/accounts.db             账号、会话、管理员
    <DATA_DIR>/users/<id>/piclog.db    每个账号自己的业务库
    <UPLOAD_ROOT>/users/<id>/          每个账号自己的原图
    <UPLOAD_ROOT>/users/<id>/thumbs/   以及缩略图

DATA_DIR 沿用旧的 DB_PATH 环境变量所在目录，部署配置不用改。
两个目录都是模块属性、在函数里现取：测试可以 monkeypatch 到临时目录。
"""
import os

import database
import thumbnail

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
