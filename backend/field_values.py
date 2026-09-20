"""日志自定义字段值的读写与查询构造。

只依赖 sqlite3，不依赖 FastAPI —— 校验失败一律抛 ValueError，
由路由层翻译成 HTTP 400。
"""

SCALAR_COLUMN = {
    "text": "value_text",
    "textarea": "value_text",
    "number": "value_num",
    "date": "value_date",
}


def load_field_values(db, log_ids, only_show_in_list=False):
    """返回 {log_id: [字段值 dict, ...]}，每个 log 的字段按 sort_order 排列。

    一次查询取回所有 log 的值，调用方不要在循环里调它。
    """
    log_ids = list(log_ids)
    if not log_ids:
        return {}

    placeholders = ",".join("?" * len(log_ids))
    extra = " AND f.show_in_list = 1" if only_show_in_list else ""
    rows = db.execute(
        f"""
        SELECT v.log_id, v.field_id, f.name, f.type, f.sort_order, f.show_in_list,
               v.value_text, v.value_num, v.value_date, v.option_id,
               o.label AS option_label
        FROM log_field_values v
        JOIN category_fields f ON f.id = v.field_id
        LEFT JOIN field_options o ON o.id = v.option_id
        WHERE v.log_id IN ({placeholders}){extra}
        ORDER BY f.sort_order, f.id, o.sort_order, o.id
        """,
        log_ids,
    ).fetchall()

    grouped = {}
    for r in rows:
        bucket = grouped.setdefault(r["log_id"], {})
        entry = bucket.get(r["field_id"])
        if entry is None:
            entry = {
                "field_id": r["field_id"],
                "name": r["name"],
                "type": r["type"],
                "sort_order": r["sort_order"],
                "show_in_list": bool(r["show_in_list"]),
                "value": [] if r["type"] == "multiselect" else None,
                "option_labels": [],
            }
            bucket[r["field_id"]] = entry

        if r["type"] == "multiselect":
            entry["value"].append(r["option_id"])
            if r["option_label"] is not None:
                entry["option_labels"].append(r["option_label"])
        elif r["type"] == "select":
            entry["value"] = r["option_id"]
            entry["option_labels"] = (
                [r["option_label"]] if r["option_label"] is not None else []
            )
        else:
            entry["value"] = r[SCALAR_COLUMN[r["type"]]]

    return {log_id: list(bucket.values()) for log_id, bucket in grouped.items()}


def _is_empty(value):
    return value is None or value == "" or value == []


def _coerce_option_id(raw_option, field_name):
    """把提交的选项值转成 int option_id；形状不对（列表、字典等）一律 ValueError。"""
    if isinstance(raw_option, bool) or isinstance(raw_option, (list, dict)):
        raise ValueError(f"字段「{field_name}」的选项 id 不合法")
    try:
        return int(raw_option)
    except (TypeError, ValueError):
        raise ValueError(f"字段「{field_name}」的选项 id 不合法")


def _check_option_belongs_to_field(db, field_id, option_id, field_name):
    row = db.execute(
        "SELECT id FROM field_options WHERE id = ? AND field_id = ?",
        (option_id, field_id),
    ).fetchone()
    if not row:
        raise ValueError(f"选项 {option_id} 不属于字段「{field_name}」")


def save_field_values(db, log_id, category_id, values):
    """全量替换某条日志的自定义字段值。

    values 的 key 是 field_id（字符串或整数皆可），value 的形状取决于字段类型：
    标量类型是标量，select 是 option_id，multiselect 是 option_id 列表。
    校验失败抛 ValueError，由路由层翻译成 400。
    """
    fields = {
        r["id"]: r
        for r in db.execute(
            "SELECT id, name, type, required FROM category_fields WHERE category_id = ?",
            (category_id,),
        ).fetchall()
    }

    normalized = {}
    for raw_key, raw_value in values.items():
        try:
            field_id = int(raw_key)
        except (TypeError, ValueError):
            raise ValueError(f"非法的字段 id: {raw_key}")
        if field_id not in fields:
            raise ValueError(f"字段 {field_id} 不属于该分类")
        normalized[field_id] = raw_value

    for field_id, field in fields.items():
        if field["required"] and _is_empty(normalized.get(field_id)):
            raise ValueError(f"字段「{field['name']}」为必填")

    for field_id, value in normalized.items():
        db.execute(
            "DELETE FROM log_field_values WHERE log_id = ? AND field_id = ?",
            (log_id, field_id),
        )
        if _is_empty(value):
            continue

        field = fields[field_id]
        ftype = field["type"]
        if ftype == "multiselect":
            if not isinstance(value, list):
                raise ValueError(f"字段「{field['name']}」需要提交列表")
            seen = set()
            for raw_option in value:
                option_id = _coerce_option_id(raw_option, field["name"])
                if option_id in seen:
                    continue
                seen.add(option_id)
                _check_option_belongs_to_field(db, field_id, option_id, field["name"])
                db.execute(
                    "INSERT INTO log_field_values (log_id, field_id, option_id) "
                    "VALUES (?, ?, ?)",
                    (log_id, field_id, option_id),
                )
        elif ftype == "select":
            option_id = _coerce_option_id(value, field["name"])
            _check_option_belongs_to_field(db, field_id, option_id, field["name"])
            db.execute(
                "INSERT INTO log_field_values (log_id, field_id, option_id) "
                "VALUES (?, ?, ?)",
                (log_id, field_id, option_id),
            )
        elif ftype == "number":
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"字段「{field['name']}」需要填数字")
            db.execute(
                "INSERT INTO log_field_values (log_id, field_id, value_num) "
                "VALUES (?, ?, ?)",
                (log_id, field_id, number),
            )
        elif ftype == "date":
            db.execute(
                "INSERT INTO log_field_values (log_id, field_id, value_date) "
                "VALUES (?, ?, ?)",
                (log_id, field_id, str(value)),
            )
        else:
            db.execute(
                "INSERT INTO log_field_values (log_id, field_id, value_text) "
                "VALUES (?, ?, ?)",
                (log_id, field_id, str(value)),
            )
