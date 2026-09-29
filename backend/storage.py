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
