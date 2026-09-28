"""后台给图片算特征向量。

一个守护线程：启动时先补算所有缺向量的图片，之后每次 notify() 被叫醒再扫一遍。
不用队列传 image_id —— 「缺什么补什么」的扫描同时覆盖了新上传、历史图片、
换模型三种情况，进程重启也不会丢任务。
"""
import logging
import os
import sqlite3
import threading

from PIL import Image

import database
import embedding
from thumbnail import THUMB_DIR, UPLOAD_DIR

log = logging.getLogger("piclog.indexer")

_wake = threading.Event()
_thread = None
# 解码失败的 image_id（非图片、文件损坏）。只记在内存里：重启后会再试一次
_failed: set[int] = set()

_MISSING_SQL = """
    SELECT i.id, i.filename
    FROM images i
    JOIN logs l ON l.id = i.log_id
    LEFT JOIN image_embeddings e ON e.image_id = i.id AND e.model = ?
    WHERE l.deleted_at IS NULL AND e.image_id IS NULL
    ORDER BY i.id
"""


def _missing(conn) -> list[tuple[int, str]]:
    rows = conn.execute(_MISSING_SQL, (embedding.MODEL_ID,)).fetchall()
    return [(r[0], r[1]) for r in rows if r[0] not in _failed]


def count_pending(conn) -> int:
    """属于有效日志、还没有当前模型向量、且没有解码失败过的图片数。"""
    return len(_missing(conn))


def _open_image(filename: str) -> Image.Image:
    # 优先用 800px 缩略图：解码快得多，模型输入只有 224px，效果没有差别
    thumb = os.path.join(THUMB_DIR, filename)
    path = thumb if os.path.isfile(thumb) else os.path.join(UPLOAD_DIR, filename)
    img = Image.open(path)
    img.load()
    return img


def process_pending() -> int:
    """补算所有缺向量的图片，返回本次写入的条数。每张图单独提交。"""
    if not embedding.available():
        return 0
    conn = sqlite3.connect(database.DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    done = 0
    try:
        for image_id, filename in _missing(conn):
            try:
                img = _open_image(filename)
                vec = embedding.embed(img)
            except embedding.EmbeddingUnavailable:
                log.exception("模型不可用，停止本轮补算")
                return done
            except Exception:
                log.warning("图片 %s（%s）无法解码，跳过", image_id, filename)
                _failed.add(image_id)
                continue
            # 推理要好几秒，这期间图片可能已被删除：只在 images 行还在时写入，
            # 否则外键约束会让 INSERT 报错
            cur = conn.execute(
                "INSERT OR REPLACE INTO image_embeddings (image_id, model, vector) "
                "SELECT ?, ?, ? WHERE EXISTS (SELECT 1 FROM images WHERE id = ?)",
                (image_id, embedding.MODEL_ID, embedding.to_blob(vec), image_id),
            )
            conn.commit()
            done += cur.rowcount
    finally:
        conn.close()
    return done


def notify():
    """有新图片入库后调用，叫醒后台线程。线程没启动时（测试、无模型）无副作用。"""
    _wake.set()


def _loop():
    while True:
        try:
            n = process_pending()
            if n:
                log.info("已为 %d 张图片建立索引", n)
        except Exception:
            log.exception("建立索引失败")
        _wake.wait()
        _wake.clear()


def start():
    global _thread
    if _thread is not None:
        return
    if os.environ.get("INDEXER_THREAD", "1") == "0":
        return
    if not embedding.available():
        log.warning("未找到模型文件 %s，以图搜图未启用", embedding.model_path())
        return
    _thread = threading.Thread(target=_loop, name="image-indexer", daemon=True)
    _thread.start()


def reset_state():
    """测试用：清空进程内状态。"""
    _failed.clear()
