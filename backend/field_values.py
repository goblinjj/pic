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
