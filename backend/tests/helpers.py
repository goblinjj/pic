import io

import numpy as np
from PIL import Image

import embedding

RED = (255, 0, 0)
BLUE = (0, 0, 255)
GREEN = (0, 255, 0)
PURPLE = (255, 0, 255)


def solid_image_bytes(color, size=(32, 32), fmt="PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


def mean_color_vector(image) -> np.ndarray:
    """假模型：前三维是平均 RGB，第四维是一个小常数（避免纯黑图得到零向量）。

    余弦相似度：红 vs 红 = 1，红 vs 紫 ≈ 0.707，红 vs 蓝/绿 ≈ 0。
    """
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32).reshape(-1, 3).mean(axis=0) / 255
    vec = np.zeros(embedding.DIM, dtype=np.float32)
    vec[:3] = rgb
    vec[3] = 0.01
    return vec
