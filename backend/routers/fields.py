from fastapi import APIRouter, Depends, HTTPException
import sqlite3
from database import get_db
from models import (
    FIELD_TYPES,
    OPTION_TYPES,
    CategoryFieldCreate,
    CategoryFieldUpdate,
    CategoryFieldOut,
    FieldOptionCreate,
    FieldOptionUpdate,
    FieldOptionOut,
    UsageOut,
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


def _get_option_or_404(db: sqlite3.Connection, option_id: int):
    row = db.execute(
        "SELECT id, field_id, label, sort_order FROM field_options WHERE id = ?",
        (option_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Option not found")
    return row


@router.post(
    "/api/fields/{field_id}/options", response_model=FieldOptionOut, status_code=201
)
def create_option(
    field_id: int,
    body: FieldOptionCreate,
    db: sqlite3.Connection = Depends(get_db),
):
    field = _get_field_or_404(db, field_id)
    if field["type"] not in OPTION_TYPES:
        raise HTTPException(400, "只有下拉/多选类型的字段才能配置选项")
    label = body.label.strip()
    if not label:
        raise HTTPException(400, "选项名称不能为空")

    cur = db.execute(
        "INSERT INTO field_options (field_id, label, sort_order) VALUES (?, ?, ?)",
        (field_id, label, body.sort_order),
    )
    db.commit()
    return dict(_get_option_or_404(db, cur.lastrowid))


@router.put("/api/options/{option_id}", response_model=FieldOptionOut)
def update_option(
    option_id: int,
    body: FieldOptionUpdate,
    db: sqlite3.Connection = Depends(get_db),
):
    _get_option_or_404(db, option_id)

    updates, params = [], []
    if body.label is not None:
        label = body.label.strip()
        if not label:
            raise HTTPException(400, "选项名称不能为空")
        updates.append("label = ?")
        params.append(label)
    if body.sort_order is not None:
        updates.append("sort_order = ?")
        params.append(body.sort_order)

    if updates:
        params.append(option_id)
        db.execute(
            f"UPDATE field_options SET {', '.join(updates)} WHERE id = ?", params
        )
        db.commit()

    return dict(_get_option_or_404(db, option_id))


@router.delete("/api/options/{option_id}", status_code=204)
def delete_option(option_id: int, db: sqlite3.Connection = Depends(get_db)):
    _get_option_or_404(db, option_id)
    db.execute("DELETE FROM field_options WHERE id = ?", (option_id,))
    db.commit()


@router.get("/api/fields/{field_id}/usage", response_model=UsageOut)
def field_usage(field_id: int, db: sqlite3.Connection = Depends(get_db)):
    _get_field_or_404(db, field_id)
    row = db.execute(
        "SELECT COUNT(DISTINCT log_id) AS c FROM log_field_values WHERE field_id = ?",
        (field_id,),
    ).fetchone()
    return {"log_count": row["c"]}


@router.get("/api/options/{option_id}/usage", response_model=UsageOut)
def option_usage(option_id: int, db: sqlite3.Connection = Depends(get_db)):
    _get_option_or_404(db, option_id)
    row = db.execute(
        "SELECT COUNT(DISTINCT log_id) AS c FROM log_field_values WHERE option_id = ?",
        (option_id,),
    ).fetchone()
    return {"log_count": row["c"]}
