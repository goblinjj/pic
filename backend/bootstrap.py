"""启动引导：每次启动都跑，里面的每一步都是幂等的。

1. 建 accounts.db 的表
2. 首次升级：把单用户时代的数据移给 1 号账号，并创建 babelingz
3. 首次配置管理员密码
4. 对每个账号的库跑 init_db（表结构增量迁移），补全缩略图
"""
import logging
import os

import accounts
import storage
import thumbnail

log = logging.getLogger("piclog.bootstrap")

INITIAL_USERNAME = "babelingz"
LEGACY_FLAG = "legacy_migrated"


class BootstrapError(RuntimeError):
    pass


def run() -> list[int]:
    os.makedirs(storage.DATA_DIR, exist_ok=True)
    conn = accounts.connect()
    try:
        accounts.init_schema(conn)
        need_first_user = not accounts.all_user_ids(conn)
        initial_password = os.environ.get("INITIAL_USER_PASSWORD", "")
        # 先检查再动文件：缺配置时旧数据原封不动
        if need_first_user:
            if not initial_password:
                raise BootstrapError(
                    f"缺少环境变量 INITIAL_USER_PASSWORD：首次启动需要它来创建账号 {INITIAL_USERNAME}"
                )
            try:
                accounts.validate_password(initial_password)
            except ValueError as exc:
                raise BootstrapError(f"INITIAL_USER_PASSWORD 不合格：{exc}")

        if accounts.get_meta(conn, LEGACY_FLAG) != "1":
            # 旧数据归 1 号账号。先搬文件再建账号、最后写完成标记：
            # 搬到一半断电的话，下次启动仍会走到这里接着搬
            storage.migrate_legacy_layout(1)
            if need_first_user:
                uid = accounts.create_user(conn, INITIAL_USERNAME, initial_password)
                if uid != 1:
                    raise BootstrapError(f"首个账号的 id 应为 1，实际为 {uid}")
            accounts.set_meta(conn, LEGACY_FLAG, "1")
        elif os.path.exists(storage.legacy_db_path()):
            # 迁移早已完成，旧位置却又冒出一个库：多半是回滚到单用户版本后又写了数据。
            # 不自动合并，只大声提示，需要人工把这段时间的数据并回 1 号账号
            log.warning(
                "发现 %s：多账号迁移后又出现了旧版本的库，其中的数据不会被读取，请人工处理",
                storage.legacy_db_path(),
            )

        admin_password = os.environ.get("ADMIN_PASSWORD", "")
        if admin_password and accounts.set_admin_password_if_missing(conn, admin_password):
            log.info("已写入管理员密码")

        user_ids = accounts.all_user_ids(conn)
    finally:
        conn.close()

    for uid in user_ids:
        storage.provision_user(uid)
        thumbnail.migrate_existing(storage.user_upload_dir(uid))
    return user_ids
