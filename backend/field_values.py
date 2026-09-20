"""日志自定义字段值的读写与查询构造。

只依赖 sqlite3，不依赖 FastAPI —— 校验失败一律抛 ValueError，
由路由层翻译成 HTTP 400。
"""

import re
from datetime import date

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


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _normalize_date(value, field_name):
    """date 的值必须是 YYYY-MM-DD。

    排序走的是 value_date 的字符串比较，格式一旦混进来就会静默排错，
    所以在写入前就拦掉。
    """
    text = str(value)
    if not _DATE_RE.match(text):
        raise ValueError(f"字段「{field_name}」需要 YYYY-MM-DD 格式的日期")
    try:
        year, month, day = (int(part) for part in text.split("-"))
        date(year, month, day)
    except ValueError:
        raise ValueError(f"字段「{field_name}」不是一个真实存在的日期")
    return text


def save_field_values(db, log_id, category_id, values):
    """替换 values 里出现过的那些字段的值（未出现的字段保持原样）。

    注意不是全量替换：只有 values 里带到的 field_id 会被先删后写，
    没带到的字段的旧值原封不动。前端每次提交都会带上该分类的全部字段，
    所以实际效果是全量替换；但 PUT {"field_values": {}} 不会清空任何东西。
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
                (log_id, field_id, _normalize_date(value, field["name"])),
            )
        else:
            db.execute(
                "INSERT INTO log_field_values (log_id, field_id, value_text) "
                "VALUES (?, ?, ?)",
                (log_id, field_id, str(value)),
            )


# 只有 number 和 date 能排序：这两种类型写入时 option_id 恒为 NULL，
# 于是唯一索引 idx_lfv_uniq(log_id, field_id, COALESCE(option_id,-1)) 保证
# 每条日志每个字段最多一行值，build_sort 的 LEFT JOIN 才不会扇出成多行、
# 在分页下静默丢行或重复行。前提是字段的 type 不可变（字段编辑不允许改类型）。
SORTABLE_COLUMN = {"number": "s.value_num", "date": "s.value_date"}


def build_option_filters(fv_params):
    """把 ['12:34', '12:35', '13:56'] 转成 (WHERE 子句列表, 参数列表)。

    同一字段内的多个选项是 OR，不同字段之间是 AND。
    对 multiselect 而言这正好等价于「包含任一选中项」。
    非法格式的条目直接忽略。
    """
    grouped = {}
    for item in fv_params or []:
        if ":" not in item:
            continue
        raw_field, raw_option = item.split(":", 1)
        if not raw_field.isdigit() or not raw_option.isdigit():
            continue
        grouped.setdefault(int(raw_field), []).append(int(raw_option))

    clauses, params = [], []
    for field_id, option_ids in grouped.items():
        placeholders = ",".join("?" * len(option_ids))
        clauses.append(
            "EXISTS (SELECT 1 FROM log_field_values v "
            f"WHERE v.log_id = l.id AND v.field_id = ? "
            f"AND v.option_id IN ({placeholders}))"
        )
        params.append(field_id)
        params.extend(option_ids)
    return clauses, params


def build_sort(db, sort_param):
    """把 '15:desc' 转成 (JOIN 子句, JOIN 参数, ORDER BY 子句)。

    只有 number 与 date 类型的字段可排序；其余一律回落到 created_at DESC。
    """
    default = ("", [], "l.created_at DESC, l.id DESC")
    if not sort_param or ":" not in sort_param:
        return default

    raw_field, direction = sort_param.split(":", 1)
    if not raw_field.isdigit() or direction not in ("asc", "desc"):
        return default

    row = db.execute(
        "SELECT type FROM category_fields WHERE id = ?", (int(raw_field),)
    ).fetchone()
    if not row or row["type"] not in SORTABLE_COLUMN:
        return default

    column = SORTABLE_COLUMN[row["type"]]
    join_sql = " LEFT JOIN log_field_values s ON s.log_id = l.id AND s.field_id = ?"
    order_sql = f"{column} {direction.upper()} NULLS LAST, l.created_at DESC, l.id DESC"
    return join_sql, [int(raw_field)], order_sql
