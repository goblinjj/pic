"""拍照以图搜图。"""
import io
import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

import embedding
import indexer
from deps import current_user_id, get_db
from image_search import MIN_SCORE, rank_logs
from models import ImageSearchOut
from routers.logs import LOG_COLUMNS, _build_log_list

router = APIRouter(tags=["search"])

# 与缩略图尺寸一致：索引就是用 800px 缩略图算的
QUERY_MAX_SIZE = (800, 800)
# 前端会先缩到 1024px 再上传，正常查询只有几百 KB
MAX_QUERY_BYTES = 20 * 1024 * 1024


def _load_query_image(content: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(content))
        # JPEG 在解码阶段就按比例缩小，免得超大图全尺寸解码吃掉几百 MB 内存
        img.draft("RGB", QUERY_MAX_SIZE)
        img.load()
    except Image.DecompressionBombError:
        # 不是 OSError 的子类，必须单独捕获
        raise HTTPException(400, "图片尺寸过大")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "无法识别的图片")
    # 先缩小再摆正：exif_transpose 会复制整张图，在小图上做省内存。
    # 限制框是正方形，先后顺序不影响结果
    img.thumbnail(QUERY_MAX_SIZE)
    # 手机竖拍的照片像素是横的，靠 EXIF 标记方向；不摆正就和库里的图对不上
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


# 同步函数：FastAPI 会放到线程池里跑，几秒的推理不会卡住事件循环
@router.post("/api/search/image", response_model=ImageSearchOut)
def search_by_image(
    file: UploadFile = File(...),
    limit: int = Query(20, ge=1, le=50),
    # 评测脚本传 -1 取回全部分数；前端不传
    min_score: float = Query(MIN_SCORE, ge=-1.0, le=1.0),
    db: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
):
    if not embedding.available():
        raise HTTPException(503, "以图搜图未启用")
    content = file.file.read(MAX_QUERY_BYTES + 1)
    if len(content) > MAX_QUERY_BYTES:
        raise HTTPException(413, "图片文件过大")
    query_img = _load_query_image(content)
    try:
        vec = embedding.embed(query_img)
    except embedding.EmbeddingUnavailable:
        raise HTTPException(503, "以图搜图未启用")

    hits, indexed = rank_logs(db, vec, limit=limit, min_score=min_score)

    items = []
    if hits:
        ids = [h.log_id for h in hits]
        placeholders = ",".join("?" * len(ids))
        rows = db.execute(
            f"SELECT {LOG_COLUMNS} FROM logs l WHERE l.id IN ({placeholders})", ids
        ).fetchall()
        logs_by_id = {log["id"]: log for log in _build_log_list(db, rows)}
        for hit in hits:
            log = logs_by_id.get(hit.log_id)
            image = next((i for i in log["images"] if i["id"] == hit.image_id), None) if log else None
            if image is None:
                continue
            items.append({"log": log, "score": round(hit.score, 4), "matched_image": image})

    return {"items": items, "indexed": indexed, "pending": indexer.count_pending(db, user_id)}
