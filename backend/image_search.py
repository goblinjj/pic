"""按查询向量给日志排序：一次查询读出全部向量，一次矩阵乘法算相似度。

几千张图的规模下全量计算只要几毫秒，远小于模型推理的耗时，
所以不做向量缓存，也不引入向量数据库。
"""
from typing import NamedTuple

import numpy as np

import embedding

# 低于此分数的不返回。初值，需用真实照片评测后调整（scripts/eval-search.py）
MIN_SCORE = 0.3


class Hit(NamedTuple):
    log_id: int
    score: float
    image_id: int


def rank_logs(db, query_vec, limit: int, min_score: float = MIN_SCORE) -> tuple[list[Hit], int]:
    """返回 (按分数降序的命中列表, 参与比对的向量数)。

    每条日志只出现一次，分数取它所有图片中的最高分，image_id 是那张图。
    """
    rows = db.execute(
        """
        SELECT e.image_id, e.vector, i.log_id
        FROM image_embeddings e
        JOIN images i ON i.id = e.image_id
        JOIN logs l ON l.id = i.log_id
        WHERE l.deleted_at IS NULL AND e.model = ?
        """,
        (embedding.MODEL_ID,),
    ).fetchall()
    rows = [r for r in rows if len(r["vector"]) == embedding.DIM * 4]
    if not rows:
        return [], 0

    matrix = np.stack([embedding.from_blob(r["vector"]) for r in rows])
    scores = matrix @ np.asarray(query_vec, dtype=np.float32)

    best: dict[int, Hit] = {}
    for row, raw in zip(rows, scores):
        score = float(raw)
        if score < min_score:
            continue
        current = best.get(row["log_id"])
        if current is None or score > current.score:
            best[row["log_id"]] = Hit(row["log_id"], score, row["image_id"])

    ranked = sorted(best.values(), key=lambda h: (-h.score, h.log_id))
    return ranked[:limit], len(rows)
