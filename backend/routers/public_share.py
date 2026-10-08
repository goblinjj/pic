"""访客侧：凭分享 token 只读浏览，无需登录。

这里只有读接口和以图搜图，写接口在分享路径下根本不存在。
范围限制收口在 scope_clause：本文件每条读日志 / 图片的 SQL 都必须拼上它，
分类级分享才不会退化成整个账号。
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

import thumbnail
from deps import ShareScope, share_scope
from models import CategoryFieldOut, CategoryOut, LogListOut, LogOut, ShareInfoOut
from routers.fields import FIELD_COLUMNS, _field_row_to_dict
from routers.files import CACHE_HEADERS
from routers.logs import LOG_COLUMNS, _build_log, query_logs

router = APIRouter(prefix="/api/share/{token}", tags=["share"])


def scope_clause(scope: ShareScope) -> tuple[list[str], list]:
    """范围条件（表别名 l）。删除过滤由 query_logs 自带，这里也加上，便于单独使用。"""
    where, params = ["l.deleted_at IS NULL"], []
    if scope.category_id is not None:
        where.append("l.category_id = ?")
        params.append(scope.category_id)
    return where, params


@router.get("/info", response_model=ShareInfoOut)
def info(scope: ShareScope = Depends(share_scope)):
    return {
        "scope": "account" if scope.category_id is None else "category",
        "category_id": scope.category_id,
        "category_name": scope.category_name,
        "owner": scope.username,
    }


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(scope: ShareScope = Depends(share_scope)):
    sql = "SELECT id, name, sort_order, created_at FROM categories"
    params: list = []
    if scope.category_id is not None:
        sql += " WHERE id = ?"
        params.append(scope.category_id)
    rows = scope.db.execute(sql + " ORDER BY sort_order, id", params).fetchall()
    return [dict(r) for r in rows]


@router.get("/categories/{category_id}/fields", response_model=list[CategoryFieldOut])
def list_fields(category_id: int, scope: ShareScope = Depends(share_scope)):
    if scope.category_id is not None and category_id != scope.category_id:
        raise HTTPException(404, "Category not found")
    rows = scope.db.execute(
        f"SELECT {FIELD_COLUMNS} FROM category_fields "
        "WHERE category_id = ? ORDER BY sort_order, id",
        (category_id,),
    ).fetchall()
    return [_field_row_to_dict(scope.db, r) for r in rows]


@router.get("/logs", response_model=LogListOut)
def list_logs(
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    status: Optional[str] = None,
    fv: list[str] = Query(default=[]),
    sort: Optional[str] = None,
    # 匿名接口：不允许一次拉全库，也不允许负 offset
    page: int = Query(1, ge=1, le=1_000_000),
    size: int = Query(20, ge=1, le=100),
    scope: ShareScope = Depends(share_scope),
):
    where, params = scope_clause(scope)
    return query_logs(
        scope.db, scope_where=where, scope_params=params,
        search=search, category_id=category_id, status=status,
        fv=fv, sort=sort, page=page, size=size,
    )


@router.get("/logs/{log_id}", response_model=LogOut)
def get_log(log_id: int, scope: ShareScope = Depends(share_scope)):
    where, params = scope_clause(scope)
    row = scope.db.execute(
        f"SELECT {LOG_COLUMNS} FROM logs l WHERE l.id = ? AND {' AND '.join(where)}",
        [log_id, *params],
    ).fetchone()
    if not row:
        raise HTTPException(404, "Log not found")
    return _build_log(scope.db, row)


def _serve(scope: ShareScope, directory: str, filename: str) -> FileResponse:
    # 比主人侧更严：除了登记在 images 表，所属日志还得在分享范围内且未删除
    where, params = scope_clause(scope)
    known = scope.db.execute(
        "SELECT 1 FROM images i JOIN logs l ON l.id = i.log_id "
        f"WHERE i.filename = ? AND {' AND '.join(where)}",
        [filename, *params],
    ).fetchone()
    path = os.path.join(directory, filename)
    if not known or os.path.basename(filename) != filename or not os.path.isfile(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path, headers=CACHE_HEADERS)


@router.get("/files/thumbs/{filename}")
def get_thumbnail(filename: str, scope: ShareScope = Depends(share_scope)):
    return _serve(scope, thumbnail.thumb_dir(scope.upload_dir), filename)


@router.get("/files/{filename}")
def get_original(filename: str, scope: ShareScope = Depends(share_scope)):
    return _serve(scope, scope.upload_dir, filename)
