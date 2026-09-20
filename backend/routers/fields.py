from fastapi import APIRouter, Depends, HTTPException
import sqlite3
from database import get_db
from models import (
    FIELD_TYPES,
    OPTION_TYPES,
    CategoryFieldCreate,
    CategoryFieldUpdate,
    CategoryFieldOut,
)

router = APIRouter(tags=["fields"])

FIELD_COLUMNS = (
    "id, category_id, name, type, required, show_in_list, sort_order"
)


def _field_row_to_dict(db: sqlite3.Connection, row) -> dict:
    field = dict(row)
    field["required"] = bool(field["required"])
    field["show_in_list"] = bool(field["show_in_list"])
    if field["type"] in OPTION_TYPES:
        opts = db.execute(
            "SELECT id, field_id, label, sort_order FROM field_options "
            "WHERE field_id = ? ORDER BY sort_order, id",
            (field["id"],),
        ).fetchall()
        field["options"] = [dict(o) for o in opts]
    else:
        field["options"] = []
    return field


def _get_field_or_404(db: sqlite3.Connection, field_id: int):
    row = db.execute(
        f"SELECT {FIELD_COLUMNS} FROM category_fields WHERE id = ?", (field_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Field not found")
    return row


@router.get("/api/categories/{category_id}/fields", response_model=list[CategoryFieldOut])
def list_fields(category_id: int, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        f"SELECT {FIELD_COLUMNS} FROM category_fields "
        "WHERE category_id = ? ORDER BY sort_order, id",
        (category_id,),
    ).fetchall()
    return [_field_row_to_dict(db, r) for r in rows]


@router.post(
    "/api/categories/{category_id}/fields",
    response_model=CategoryFieldOut,
    status_code=201,
)
def create_field(
    category_id: int,
    body: CategoryFieldCreate,
    db: sqlite3.Connection = Depends(get_db),
):
    cat = db.execute(
        "SELECT id FROM categories WHERE id = ?", (category_id,)
    ).fetchone()
    if not cat:
        raise HTTPException(404, "Category not found")
    if body.type not in FIELD_TYPES:
        raise HTTPException(400, f"Invalid field type: {body.type}")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "字段名称不能为空")

    cur = db.execute(
        "INSERT INTO category_fields "
        "(category_id, name, type, required, show_in_list, sort_order) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (category_id, name, body.type, int(body.required),
         int(body.show_in_list), body.sort_order),
    )
    db.commit()
    return _field_row_to_dict(db, _get_field_or_404(db, cur.lastrowid))


@router.put("/api/fields/{field_id}", response_model=CategoryFieldOut)
def update_field(
    field_id: int,
    body: CategoryFieldUpdate,
    db: sqlite3.Connection = Depends(get_db),
):
    _get_field_or_404(db, field_id)

    updates, params = [], []
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "字段名称不能为空")
        updates.append("name = ?")
        params.append(name)
    if body.required is not None:
        updates.append("required = ?")
        params.append(int(body.required))
    if body.show_in_list is not None:
        updates.append("show_in_list = ?")
        params.append(int(body.show_in_list))
    if body.sort_order is not None:
        updates.append("sort_order = ?")
        params.append(body.sort_order)

    if updates:
        params.append(field_id)
        db.execute(
            f"UPDATE category_fields SET {', '.join(updates)} WHERE id = ?", params
        )
        db.commit()

    return _field_row_to_dict(db, _get_field_or_404(db, field_id))


@router.delete("/api/fields/{field_id}", status_code=204)
def delete_field(field_id: int, db: sqlite3.Connection = Depends(get_db)):
    _get_field_or_404(db, field_id)
    db.execute("DELETE FROM category_fields WHERE id = ?", (field_id,))
    db.commit()
