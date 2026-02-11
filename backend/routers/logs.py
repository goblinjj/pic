from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
import sqlite3
import uuid
import os
from typing import Optional
from database import get_db
from models import LogOut, LogListOut, LogUpdate, StatusUpdate, ImageOut

router = APIRouter(prefix="/api/logs", tags=["logs"])

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")


def _build_log(db: sqlite3.Connection, log_row) -> dict:
    log = dict(log_row)
    cat = db.execute(
        "SELECT name FROM categories WHERE id = ?", (log["category_id"],)
    ).fetchone()
    log["category_name"] = cat["name"] if cat else ""
    imgs = db.execute(
        "SELECT id, log_id, filename, original_name, created_at FROM images WHERE log_id = ? ORDER BY id",
        (log["id"],),
    ).fetchall()
    log["images"] = [dict(i) for i in imgs]
    return log


@router.get("", response_model=LogListOut)
def list_logs(
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    db: sqlite3.Connection = Depends(get_db),
):
    where, params = [], []
    if search:
        where.append("l.description LIKE ?")
        params.append(f"%{search}%")
    if category_id is not None:
        where.append("l.category_id = ?")
        params.append(category_id)
    if status:
        where.append("l.status = ?")
        params.append(status)

    where_clause = (" WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(
        f"SELECT COUNT(*) as c FROM logs l{where_clause}", params
    ).fetchone()["c"]

    offset = (page - 1) * size
    rows = db.execute(
        f"SELECT l.id, l.category_id, l.description, l.external_link, l.status, l.created_at, l.updated_at "
        f"FROM logs l{where_clause} ORDER BY l.created_at DESC LIMIT ? OFFSET ?",
        params + [size, offset],
    ).fetchall()

    items = [_build_log(db, r) for r in rows]
    return {"items": items, "total": total, "page": page, "size": size}


@router.post("", response_model=LogOut, status_code=201)
async def create_log(
    category_id: int = Form(...),
    description: str = Form(""),
    external_link: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    db: sqlite3.Connection = Depends(get_db),
):
    cat = db.execute(
        "SELECT id FROM categories WHERE id = ?", (category_id,)
    ).fetchone()
    if not cat:
        raise HTTPException(400, "Invalid category")

    cur = db.execute(
        "INSERT INTO logs (category_id, description, external_link) VALUES (?, ?, ?)",
        (category_id, description, external_link),
    )
    log_id = cur.lastrowid
    db.commit()

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    for f in files:
        if not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1]
        stored_name = f"{uuid.uuid4().hex}{ext}"
        path = os.path.join(UPLOAD_DIR, stored_name)
        content = await f.read()
        with open(path, "wb") as out:
            out.write(content)
        db.execute(
            "INSERT INTO images (log_id, filename, original_name) VALUES (?, ?, ?)",
            (log_id, stored_name, f.filename),
        )
    db.commit()

    row = db.execute(
        "SELECT id, category_id, description, external_link, status, created_at, updated_at FROM logs WHERE id = ?",
        (log_id,),
    ).fetchone()
    return _build_log(db, row)


@router.get("/{log_id}", response_model=LogOut)
def get_log(log_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute(
        "SELECT id, category_id, description, external_link, status, created_at, updated_at FROM logs WHERE id = ?",
        (log_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Log not found")
    return _build_log(db, row)


@router.put("/{log_id}", response_model=LogOut)
def update_log(
    log_id: int,
    body: LogUpdate,
    db: sqlite3.Connection = Depends(get_db),
):
    existing = db.execute("SELECT id FROM logs WHERE id = ?", (log_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "Log not found")

    updates, params = [], []
    if body.category_id is not None:
        updates.append("category_id = ?")
        params.append(body.category_id)
    if body.description is not None:
        updates.append("description = ?")
        params.append(body.description)
    if body.external_link is not None:
        updates.append("external_link = ?")
        params.append(body.external_link)
    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(log_id)
        db.execute(
            f"UPDATE logs SET {', '.join(updates)} WHERE id = ?", params
        )
        db.commit()

    row = db.execute(
        "SELECT id, category_id, description, external_link, status, created_at, updated_at FROM logs WHERE id = ?",
        (log_id,),
    ).fetchone()
    return _build_log(db, row)


@router.patch("/{log_id}/status", response_model=LogOut)
def toggle_status(
    log_id: int,
    body: StatusUpdate,
    db: sqlite3.Connection = Depends(get_db),
):
    if body.status not in ("pending", "completed"):
        raise HTTPException(400, "Invalid status")
    existing = db.execute("SELECT id FROM logs WHERE id = ?", (log_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "Log not found")
    db.execute(
        "UPDATE logs SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (body.status, log_id),
    )
    db.commit()
    row = db.execute(
        "SELECT id, category_id, description, external_link, status, created_at, updated_at FROM logs WHERE id = ?",
        (log_id,),
    ).fetchone()
    return _build_log(db, row)


@router.delete("/{log_id}", status_code=204)
def delete_log(log_id: int, db: sqlite3.Connection = Depends(get_db)):
    existing = db.execute("SELECT id FROM logs WHERE id = ?", (log_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "Log not found")
    imgs = db.execute(
        "SELECT filename FROM images WHERE log_id = ?", (log_id,)
    ).fetchall()
    for img in imgs:
        path = os.path.join(UPLOAD_DIR, img["filename"])
        if os.path.exists(path):
            os.remove(path)
    db.execute("DELETE FROM logs WHERE id = ?", (log_id,))
    db.commit()
