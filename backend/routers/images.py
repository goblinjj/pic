from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import sqlite3
import uuid
import os
import indexer
from deps import get_db, get_upload_dir
from models import ImageOut
from thumbnail import generate_thumbnail, delete_thumbnail

router = APIRouter(tags=["images"])


@router.post("/api/logs/{log_id}/images", response_model=list[ImageOut], status_code=201)
async def upload_images(
    log_id: int,
    files: list[UploadFile] = File(...),
    db: sqlite3.Connection = Depends(get_db),
    upload_dir: str = Depends(get_upload_dir),
):
    existing = db.execute("SELECT id FROM logs WHERE id = ?", (log_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "Log not found")

    os.makedirs(upload_dir, exist_ok=True)
    result = []
    for f in files:
        if not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1]
        stored_name = f"{uuid.uuid4().hex}{ext}"
        path = os.path.join(upload_dir, stored_name)
        content = await f.read()
        with open(path, "wb") as out:
            out.write(content)
        generate_thumbnail(upload_dir, stored_name)
        cur = db.execute(
            "INSERT INTO images (log_id, filename, original_name) VALUES (?, ?, ?)",
            (log_id, stored_name, f.filename),
        )
        result.append({
            "id": cur.lastrowid,
            "log_id": log_id,
            "filename": stored_name,
            "original_name": f.filename,
            "created_at": "",
        })
    db.commit()
    indexer.notify()

    rows = db.execute(
        "SELECT id, log_id, filename, original_name, created_at FROM images WHERE log_id = ? ORDER BY id DESC LIMIT ?",
        (log_id, len(result)),
    ).fetchall()
    return [dict(r) for r in rows]


@router.delete("/api/images/{image_id}", status_code=204)
def delete_image(
    image_id: int,
    db: sqlite3.Connection = Depends(get_db),
    upload_dir: str = Depends(get_upload_dir),
):
    row = db.execute(
        "SELECT id, filename FROM images WHERE id = ?", (image_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Image not found")
    path = os.path.join(upload_dir, row["filename"])
    if os.path.exists(path):
        os.remove(path)
    delete_thumbnail(upload_dir, row["filename"])
    db.execute("DELETE FROM images WHERE id = ?", (image_id,))
    db.commit()
