from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
import json
import sqlite3
import uuid
import os
from typing import Optional
from database import get_db
from models import LogOut, LogListOut, LogUpdate, StatusUpdate, ImageOut
from thumbnail import generate_thumbnail
from field_values import load_field_values, save_field_values

router = APIRouter(prefix="/api/logs", tags=["logs"])

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")

LOG_COLUMNS = (
    "l.id, l.category_id, l.description, l.external_link, "
    "l.status, l.created_at, l.updated_at"
)


def _build_log(db: sqlite3.Connection, log_row) -> dict:
    log = dict(log_row)
    cat = db.execute(
        "SELECT name FROM categories WHERE id = ?", (log["category_id"],)
    ).fetchone()
    log["category_name"] = cat["name"] if cat else ""
    imgs = db.execute(
        "SELECT id, log_id, filename, original_name, created_at FROM images "
        "WHERE log_id = ? ORDER BY id",
        (log["id"],),
    ).fetchall()
    log["images"] = [dict(i) for i in imgs]
    log["field_values"] = load_field_values(db, [log["id"]]).get(log["id"], [])
    return log


def _apply_field_values(db, log_id: int, category_id: int, values: dict):
    try:
        save_field_values(db, log_id, category_id, values)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("", response_model=LogListOut)
def list_logs(
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    db: sqlite3.Connection = Depends(get_db),
):
    where, params = ["l.deleted_at IS NULL"], []
    if search:
        where.append("l.description LIKE ?")
        params.append(f"%{search}%")
    if category_id is not None:
        where.append("l.category_id = ?")
        params.append(category_id)
    if status:
        where.append("l.status = ?")
        params.append(status)

    where_clause = " WHERE " + " AND ".join(where)

    total = db.execute(
        f"SELECT COUNT(*) as c FROM logs l{where_clause}", params
    ).fetchone()["c"]

    offset = (page - 1) * size
    rows = db.execute(
        f"SELECT {LOG_COLUMNS} FROM logs l{where_clause} "
        f"ORDER BY l.created_at DESC LIMIT ? OFFSET ?",
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
    field_values: str = Form("{}"),
    db: sqlite3.Connection = Depends(get_db),
):
    cat = db.execute(
        "SELECT id FROM categories WHERE id = ?", (category_id,)
    ).fetchone()
    if not cat:
        raise HTTPException(400, "Invalid category")

    try:
        parsed_values = json.loads(field_values or "{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "field_values 不是合法的 JSON")
    if not isinstance(parsed_values, dict):
        raise HTTPException(400, "field_values 必须是对象")

    try:
        cur = db.execute(
            "INSERT INTO logs (category_id, description, external_link) VALUES (?, ?, ?)",
            (category_id, description, external_link),
        )
        log_id = cur.lastrowid

        _apply_field_values(db, log_id, category_id, parsed_values)

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
            generate_thumbnail(stored_name)
            db.execute(
                "INSERT INTO images (log_id, filename, original_name) VALUES (?, ?, ?)",
                (log_id, stored_name, f.filename),
            )
    except HTTPException:
        db.rollback()
        raise

    db.commit()

    row = db.execute(
        f"SELECT {LOG_COLUMNS} FROM logs l WHERE l.id = ?", (log_id,)
    ).fetchone()
    return _build_log(db, row)


@router.get("/{log_id}", response_model=LogOut)
def get_log(log_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute(
        f"SELECT {LOG_COLUMNS} FROM logs l WHERE l.id = ? AND l.deleted_at IS NULL",
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
    existing = db.execute(
        "SELECT category_id FROM logs WHERE id = ? AND deleted_at IS NULL", (log_id,)
    ).fetchone()
    if not existing:
        raise HTTPException(404, "Log not found")
    current_category = existing["category_id"]

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

    try:
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(log_id)
            db.execute(
                f"UPDATE logs SET {', '.join(updates)} WHERE id = ?", params
            )

        target_category = body.category_id if body.category_id is not None else current_category

        if body.field_values is not None:
            _apply_field_values(db, log_id, target_category, body.field_values)

        if body.category_id is not None and body.category_id != current_category:
            # 切换分类要清掉不属于新分类的旧字段值，不能靠前端清表单状态
            db.execute(
                "DELETE FROM log_field_values WHERE log_id = ? AND field_id NOT IN "
                "(SELECT id FROM category_fields WHERE category_id = ?)",
                (log_id, target_category),
            )
    except HTTPException:
        db.rollback()
        raise

    db.commit()

    row = db.execute(
        f"SELECT {LOG_COLUMNS} FROM logs l WHERE l.id = ?", (log_id,)
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
    existing = db.execute("SELECT id FROM logs WHERE id = ? AND deleted_at IS NULL", (log_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "Log not found")
    db.execute(
        "UPDATE logs SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (body.status, log_id),
    )
    db.commit()
    row = db.execute(
        f"SELECT {LOG_COLUMNS} FROM logs l WHERE l.id = ?", (log_id,)
    ).fetchone()
    return _build_log(db, row)


@router.delete("/{log_id}", status_code=204)
def delete_log(log_id: int, db: sqlite3.Connection = Depends(get_db)):
    existing = db.execute("SELECT id FROM logs WHERE id = ? AND deleted_at IS NULL", (log_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "Log not found")
    db.execute(
        "UPDATE logs SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?", (log_id,)
    )
    db.commit()
