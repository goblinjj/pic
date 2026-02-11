import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from database import init_db
from routers import categories, logs, images
from thumbnail import migrate_existing

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
STATIC_DIR = os.environ.get("STATIC_DIR", "/app/static")

app = FastAPI(title="PicLog")

app.include_router(categories.router)
app.include_router(logs.router)
app.include_router(images.router)

os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.on_event("startup")
def startup():
    init_db()
    migrate_existing()


if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
