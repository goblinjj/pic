from fastapi import APIRouter, Depends, HTTPException
import sqlite3
from database import get_db
from models import CategoryCreate, CategoryUpdate, CategoryOut

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT id, name, sort_order, created_at FROM categories ORDER BY sort_order, id"
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryCreate, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO categories (name, sort_order) VALUES (?, ?)",
        (body.name, body.sort_order),
    )
    db.commit()
    row = db.execute(
        "SELECT id, name, sort_order, created_at FROM categories WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    return dict(row)


@router.put("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    body: CategoryUpdate,
    db: sqlite3.Connection = Depends(get_db),
):
    existing = db.execute(
        "SELECT id FROM categories WHERE id = ?", (category_id,)
    ).fetchone()
    if not existing:
        raise HTTPException(404, "Category not found")

    updates, params = [], []
    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name)
    if body.sort_order is not None:
        updates.append("sort_order = ?")
        params.append(body.sort_order)
    if updates:
        params.append(category_id)
        db.execute(
            f"UPDATE categories SET {', '.join(updates)} WHERE id = ?", params
        )
        db.commit()

    row = db.execute(
        "SELECT id, name, sort_order, created_at FROM categories WHERE id = ?",
        (category_id,),
    ).fetchone()
    return dict(row)


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, db: sqlite3.Connection = Depends(get_db)):
    existing = db.execute(
        "SELECT id FROM categories WHERE id = ?", (category_id,)
    ).fetchone()
    if not existing:
        raise HTTPException(404, "Category not found")
    log_count = db.execute(
        "SELECT COUNT(*) as c FROM logs WHERE category_id = ?", (category_id,)
    ).fetchone()["c"]
    if log_count > 0:
        raise HTTPException(400, "Category has logs, cannot delete")
    db.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    db.commit()
