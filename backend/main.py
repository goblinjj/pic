import logging
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import admin
import bootstrap
import indexer
from routers import auth, categories, logs, images, fields, search, files

STATIC_DIR = os.environ.get("STATIC_DIR", "/app/static")
log = logging.getLogger("piclog")


def create_app() -> FastAPI:
    app = FastAPI(title="PicLog")

    app.include_router(auth.router)
    app.include_router(categories.router)
    app.include_router(logs.router)
    app.include_router(images.router)
    app.include_router(fields.router)
    app.include_router(search.router)
    app.include_router(files.router)

    # 必须在 SPA 兜底路由之前注册
    admin_path = admin.configured_path()
    if admin_path:
        app.include_router(admin.build_router(admin_path))
    else:
        log.warning("未配置 ADMIN_PATH，管理后台未启用")

    @app.on_event("startup")
    def startup():
        bootstrap.run()
        indexer.start()

    if os.path.isdir(STATIC_DIR):
        app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

        static_root = os.path.realpath(STATIC_DIR)

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # 路径参数已被 URL 解码，..%2F 会变成 ../：必须确认落在静态目录内，
            # 否则能读到隔壁的 accounts.db 和各账号的库
            file_path = os.path.realpath(os.path.join(static_root, full_path))
            inside = file_path.startswith(static_root + os.sep)
            if inside and os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(static_root, "index.html"))

    return app


app = create_app()
