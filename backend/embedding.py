"""图像特征向量：唯一接触 ONNX 模型的模块。

模型是 DINOv2-small（onnx-community/dinov2-small 的 onnx/model.onnx），
取 CLS token 作为整张图的 384 维特征。向量都做 L2 归一化，
两个向量的点积就是余弦相似度。
"""
import os
import threading

import numpy as np
from PIL import Image

MODEL_ID = "dinov2-small-v1"
DIM = 384
DEFAULT_MODEL_PATH = "/app/data/models/dinov2-small.onnx"

# 与模型自带的 preprocessor_config.json 一致：短边缩到 256，中心裁 224
RESIZE_SHORT_EDGE = 256
CROP_SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# NAS 只有 4 核：推理最多占 2 个，给 Web 请求留余量
NUM_THREADS = 2


class EmbeddingUnavailable(Exception):
    """模型文件缺失或加载失败。"""


_lock = threading.Lock()
_session = None
_override = None


def model_path() -> str:
    # 每次调用时读环境变量，测试可以随时切换
    return os.environ.get("MODEL_PATH", DEFAULT_MODEL_PATH)


def set_embedder(fn):
    """测试用：注入 fn(PIL.Image) -> 向量，替代真实模型；传 None 恢复。"""
    global _override
    _override = fn


def available() -> bool:
    return _override is not None or os.path.isfile(model_path())


def preprocess(image: Image.Image) -> np.ndarray:
    """PIL 图片 → (1, 3, 224, 224) float32。

    先在原图坐标里算出中心裁剪框，再一步缩放到 224：结果与「整图缩放后再裁」
    等价（实测余弦相似度 0.9986），但极端长宽比的图不会先被放大成巨图吃内存。
    """
    img = image.convert("RGB")
    w, h = img.size
    side = min(w, h) * CROP_SIZE / RESIZE_SHORT_EDGE
    left = (w - side) / 2
    top = (h - side) / 2
    img = img.resize(
        (CROP_SIZE, CROP_SIZE), Image.BICUBIC, box=(left, top, left + side, top + side)
    )
    arr = (np.asarray(img, dtype=np.float32) / 255.0 - MEAN) / STD
    return arr.transpose(2, 0, 1)[np.newaxis]


def _get_session():
    global _session
    if _session is None:
        path = model_path()
        if not os.path.isfile(path):
            raise EmbeddingUnavailable(f"模型文件不存在：{path}")
        # 延迟导入：没有模型时（测试、未放模型的部署）不必加载 onnxruntime
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = NUM_THREADS
        opts.inter_op_num_threads = 1
        try:
            _session = ort.InferenceSession(
                path, sess_options=opts, providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            raise EmbeddingUnavailable(f"模型加载失败：{exc}") from exc
    return _session


def embed(image: Image.Image) -> np.ndarray:
    """返回 L2 归一化的 float32 向量，形状 (DIM,)。所有推理串行执行。"""
    with _lock:
        if _override is not None:
            vec = _override(image)
        else:
            out = _get_session().run(
                ["last_hidden_state"], {"pixel_values": preprocess(image)}
            )
            vec = out[0][0, 0]
    vec = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm > 0 else vec


def to_blob(vec) -> bytes:
    return np.asarray(vec, dtype="<f4").tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype="<f4")
