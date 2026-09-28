# 拍照以图搜图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户拍一张照片（或从相册选图），按相似度找到库里记录过的同一件实物所在的日志。

**Architecture:** 新模块 `embedding.py` 用 onnxruntime 在 CPU 上跑 DINOv2-small，把图片变成 384 维 L2 归一化向量；`indexer.py` 的后台线程把每张图片的向量存进 SQLite 新表 `image_embeddings`；`POST /api/search/image` 把查询照片变成向量，与全部向量做一次矩阵乘法、按日志聚合取最高分。前端新增搜索页 `/search/image`，入口是列表页搜索框旁的相机按钮。

**Tech Stack:** FastAPI、SQLite、Pillow、onnxruntime 1.30.0、numpy 2.5.3；Vue 3 + vue-router + Tailwind 4。

**Spec:** `docs/superpowers/specs/2026-09-29-image-search-design.md`

## Global Constraints

- 模型：`onnx-community/dinov2-small` 的 `onnx/model.onnx`，88532934 字节，sha256 `f22797eabf810a75e41de68d378541ebea372122b25c4ce3ef25ff618250c20a`
- 模型输入名 `pixel_values`（`float32`，NCHW），输出名 `last_hidden_state`，形状 `(1, 257, 384)`；取 `[0, 0]`（CLS token）
- 模型标识 `MODEL_ID = "dinov2-small-v1"`，向量维度 `DIM = 384`，以 little-endian float32 存 BLOB
- 模型路径环境变量 `MODEL_PATH`，默认 `/app/data/models/dinov2-small.onnx`；不进 git，不在 Docker 构建时下载
- onnxruntime `intra_op_num_threads = 2`（NAS 是 4 核 Celeron J3455）
- 依赖版本锁定：`onnxruntime==1.30.0`、`numpy==2.5.3`（已确认 cp312 manylinux x86_64 与 cp314 macOS arm64 均有 wheel）
- 模型缺失或损坏时：应用照常启动、上传照常成功、搜索返回 503 `"以图搜图未启用"`
- 搜索只包含 `logs.deleted_at IS NULL` 的日志；查询照片不落盘
- 查询图片服务端缩到 800×800 以内（与缩略图 `THUMB_SIZE` 相同）；索引用 `uploads/thumbs/` 下的缩略图，缩略图不存在才用原图
- `limit` 默认 20，范围 1–50；`MIN_SCORE` 初值 0.3；`min_score` 查询参数范围 -1–1
- 前端相似度档位初值：≥0.75「很可能是同一件」、≥0.5「相似」、其余「有点像」
- 文件选择框用 `accept="image/*"`，**不加** `capture` 属性
- 所有用户可见文案、代码注释用简体中文，与现有代码一致
- 后端测试命令：`cd backend && .venv/bin/pytest tests -q`；当前基线 77 passed
- 提交信息结尾加：`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
- **不要 `git push`**：本仓库的 pre-push hook 会自动部署到 NAS。部署只在 Task 7 经用户确认后进行

## Review Focus

1. **手机竖拍照片带 EXIF 方向标记** —— 查询图必须先按 EXIF 摆正再提特征，否则同一件东西横过来就搜不到。测试在 Task 3（`test_exif_orientation_is_applied`）。
2. **不支持或损坏的查询图片**（桌面端选了 HEIC、截断的 JPEG、随便什么文件）—— 应返回 400 和中文提示，而不是 500。测试在 Task 3（`test_non_image_returns_400`、`test_truncated_jpeg_returns_400`）。
3. **超大像素的图片**（解压炸弹）—— `DecompressionBombError` 不是 `OSError` 的子类，必须单独捕获并返回 400「图片尺寸过大」。测试在 Task 3（`test_oversized_image_returns_400`）。
4. **后台补算期间图片被删除** —— 推理要好几秒，期间图片行可能已不存在；写入时不能触发外键错误，也不能让后台线程崩掉。测试在 Task 2（`test_image_deleted_during_inference_is_not_written`）。
5. **刚部署、索引还是空的**（所有图片都在 pending）—— 搜索应返回 200、空结果和正确的 `pending` 数，前端显示提示条而不是报错。测试在 Task 3（`test_empty_index_returns_pending_count`）。

---

## File Structure

| 文件 | 动作 | 职责 |
| --- | --- | --- |
| `backend/embedding.py` | 新建 | 唯一接触模型：预处理、推理、归一化、向量与 BLOB 互转、测试注入 |
| `backend/indexer.py` | 新建 | 后台线程；扫描缺向量的图片并补算；`count_pending()` |
| `backend/image_search.py` | 新建 | 纯排序逻辑：读向量、矩阵乘法、按日志聚合；`MIN_SCORE` |
| `backend/routers/search.py` | 新建 | `POST /api/search/image`：读图、校验、调用上面两个模块、组装响应 |
| `backend/database.py` | 修改 | 建 `image_embeddings` 表 |
| `backend/models.py` | 修改 | `ImageSearchHit`、`ImageSearchOut` |
| `backend/main.py` | 修改 | 注册 search 路由；startup 启动 indexer |
| `backend/routers/images.py` | 修改 | 上传提交后 `indexer.notify()` |
| `backend/routers/logs.py` | 修改 | 新建日志提交后 `indexer.notify()` |
| `backend/requirements.txt` | 修改 | 加 onnxruntime、numpy |
| `backend/tests/conftest.py` | 修改 | 关闭后台线程、指向不存在的模型、`fake_embedder` fixture |
| `backend/tests/helpers.py` | 新建 | 生成测试图片、按平均颜色生成假向量 |
| `backend/tests/test_embedding.py` | 新建 | embedding 单元测试 + 真实模型冒烟测试 |
| `backend/tests/test_indexer.py` | 新建 | 索引写入、级联删除、补算、pending |
| `backend/tests/test_image_search.py` | 新建 | 搜索接口 |
| `scripts/fetch-model.sh` | 新建 | 下载、校验、上传模型到 NAS（或放到本地开发目录） |
| `scripts/eval-search.py` | 新建 | 用真实照片评测排名与分数分布 |
| `docker-compose.yml` | 修改 | 显式声明 `MODEL_PATH` |
| `scripts/setup-dev.sh` | 修改 | 开发说明里加上模型相关命令 |
| `frontend/src/components/LogCard.vue` | 新建 | 从 `LogList.vue` 抽出的日志卡片，支持指定封面图和角标插槽 |
| `frontend/src/views/LogList.vue` | 修改 | 使用 `LogCard`；搜索框旁加相机按钮 |
| `frontend/src/api.js` | 修改 | 错误对象带 `status`；`searchByImage()` |
| `frontend/src/imageCompress.js` | 修改 | `doCompress` 参数化；新增 `shrinkForSearch()` |
| `frontend/src/imageSearch.js` | 新建 | 搜索状态 store、`searchByPhoto()`、`retry()`、`scoreLabel()` |
| `frontend/src/components/CameraSearchButton.vue` | 新建 | 相机按钮 + 隐藏的文件选择框 |
| `frontend/src/views/ImageSearch.vue` | 新建 | 搜索结果页 |
| `frontend/src/router.js` | 修改 | 注册 `/search/image` |

---

### Task 0: 在 NAS 上验证 onnxruntime 能跑、速度可接受

J3455 不支持 AVX2，onnxruntime 1.30 的预编译包能否在它上面运行、单张要几秒，必须先实测。如果跑不了或太慢，后面所有任务的方案都要重新讨论。

**这一步会在 NAS 上临时写文件并运行一次性容器。执行前必须先向用户说明并获得同意。**

**Files:** 无（不改仓库）

- [ ] **Step 1: 向用户说明并征得同意**

说明内容：会把约 85MB 的模型传到 NAS 的 `/tmp/piclog-ort-check/`，用 `python:3.12-slim`（现有镜像的基础镜像）起一个 `--rm` 容器装 onnxruntime 跑 5 次推理，完成后删除临时目录。不影响正在运行的 piclog 容器。

- [ ] **Step 2: 本机下载并校验模型**

```bash
mkdir -p ~/.cache/piclog
curl -fL --retry 3 -o ~/.cache/piclog/dinov2-small.onnx \
  https://huggingface.co/onnx-community/dinov2-small/resolve/main/onnx/model.onnx
shasum -a 256 ~/.cache/piclog/dinov2-small.onnx
```

Expected: `f22797eabf810a75e41de68d378541ebea372122b25c4ce3ef25ff618250c20a`

- [ ] **Step 3: 传到 NAS 临时目录**

```bash
ssh -o BatchMode=yes root@192.168.8.10 'mkdir -p /tmp/piclog-ort-check && cat > /tmp/piclog-ort-check/m.onnx' \
  < ~/.cache/piclog/dinov2-small.onnx
```

- [ ] **Step 4: 在一次性容器里跑推理并计时**

```bash
ssh -o BatchMode=yes root@192.168.8.10 'export PATH=/usr/local/bin:/usr/bin:/bin:$PATH; docker run --rm -v /tmp/piclog-ort-check:/m python:3.12-slim sh -c "pip install -q onnxruntime==1.30.0 numpy==2.5.3 && python -c \"
import time, numpy as np, onnxruntime as ort
o = ort.SessionOptions(); o.intra_op_num_threads = 2; o.inter_op_num_threads = 1
t = time.time(); s = ort.InferenceSession(\\\"/m/m.onnx\\\", o, providers=[\\\"CPUExecutionProvider\\\"]); print(\\\"load\\\", round(time.time() - t, 2))
x = np.random.rand(1, 3, 224, 224).astype(\\\"float32\\\")
for i in range(5):
    t = time.time(); y = s.run([\\\"last_hidden_state\\\"], {\\\"pixel_values\\\": x})[0]; print(\\\"run\\\", round(time.time() - t, 2), y.shape)
\""'
```

Expected: 打印 `load` 耗时和 5 行 `run <秒数> (1, 257, 384)`，没有 `Illegal instruction`。

- [ ] **Step 5: 清理 NAS 临时目录**

```bash
ssh -o BatchMode=yes root@192.168.8.10 'rm -rf /tmp/piclog-ort-check'
```

- [ ] **Step 6: 判定**

- 能跑，且后 4 次 `run` 的平均值 ≤ 5 秒 → 继续 Task 1，把实测耗时告诉用户
- 报 `Illegal instruction` / 崩溃，或平均值 > 5 秒 → **停下**，把输出告诉用户，讨论换 `model_int8.onnx`、降低 onnxruntime 版本或其他方案，不要继续后面的任务

---

### Task 1: embedding 模块

**Files:**
- Create: `backend/embedding.py`
- Create: `backend/tests/helpers.py`
- Create: `backend/tests/test_embedding.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: 无
- Produces（后续任务使用）:
  - `embedding.MODEL_ID: str`、`embedding.DIM: int`
  - `embedding.EmbeddingUnavailable(Exception)`
  - `embedding.model_path() -> str`
  - `embedding.available() -> bool`
  - `embedding.embed(image: PIL.Image.Image) -> np.ndarray`（shape `(384,)`，float32，L2 归一化）
  - `embedding.set_embedder(fn | None)`
  - `embedding.to_blob(vec) -> bytes`、`embedding.from_blob(blob: bytes) -> np.ndarray`
  - `tests/helpers.py`: `solid_image_bytes(color, size=(32, 32), fmt="PNG") -> bytes`、`mean_color_vector(image) -> np.ndarray`
  - `conftest.py` fixture：`fake_embedder`

- [ ] **Step 1: 加依赖并安装**

`backend/requirements.txt` 末尾追加两行：

```
onnxruntime==1.30.0
numpy==2.5.3
```

Run: `cd backend && .venv/bin/pip install -q -r requirements-dev.txt`
Expected: 安装成功，无报错。

- [ ] **Step 2: 改 conftest —— 测试环境默认无模型、无后台线程**

在 `backend/tests/conftest.py` 中，紧跟 `os.environ["STATIC_DIR"] = ...` 那一行之后加：

```python
# 默认没有模型：需要向量的测试用 fake_embedder 注入假模型
os.environ["MODEL_PATH"] = os.path.join(_TMP, "no-model.onnx")
# 测试里不启动后台索引线程，改为直接调用 indexer.process_pending()，避免依赖线程时序
os.environ["INDEXER_THREAD"] = "0"
```

在文件末尾追加：

```python
@pytest.fixture()
def fake_embedder():
    """注入按图片平均颜色生成向量的假模型：颜色相同 = 相似度 1，红与蓝 ≈ 0。"""
    import embedding
    from tests.helpers import mean_color_vector

    embedding.set_embedder(mean_color_vector)
    yield
    embedding.set_embedder(None)
```

- [ ] **Step 3: 写测试辅助函数**

Create `backend/tests/helpers.py`:

```python
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
```

- [ ] **Step 4: 写失败的测试**

Create `backend/tests/test_embedding.py`:

```python
import io
import os

import numpy as np
import pytest
from PIL import Image, ImageDraw

import embedding


@pytest.fixture(autouse=True)
def fresh_session():
    """每个测试前后都丢掉缓存的 ONNX session，互不影响。"""
    embedding._session = None
    yield
    embedding._session = None
    embedding.set_embedder(None)


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "P", "CMYK"])
def test_preprocess_handles_all_color_modes(mode):
    x = embedding.preprocess(Image.new(mode, (300, 200)))
    assert x.shape == (1, 3, 224, 224)
    assert x.dtype == np.float32


@pytest.mark.parametrize("size", [(1, 800), (800, 1), (1, 1), (4000, 3000)])
def test_preprocess_handles_extreme_sizes(size):
    assert embedding.preprocess(Image.new("RGB", size)).shape == (1, 3, 224, 224)


def test_preprocess_normalizes_with_imagenet_stats():
    x = embedding.preprocess(Image.new("RGB", (64, 64), (255, 255, 255)))
    expected = (1.0 - embedding.MEAN) / embedding.STD
    np.testing.assert_allclose(x[0, :, 112, 112], expected, rtol=1e-5)


def test_embed_returns_l2_normalized_float32():
    embedding.set_embedder(lambda img: [3.0, 4.0] + [0.0] * (embedding.DIM - 2))
    vec = embedding.embed(Image.new("RGB", (8, 8)))
    assert vec.shape == (embedding.DIM,)
    assert vec.dtype == np.float32
    np.testing.assert_allclose(vec[:2], [0.6, 0.8], rtol=1e-6)


def test_available_is_false_without_model_file(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "missing.onnx"))
    assert embedding.available() is False


def test_available_is_true_with_injected_embedder(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "missing.onnx"))
    embedding.set_embedder(lambda img: np.ones(embedding.DIM))
    assert embedding.available() is True


def test_embed_raises_unavailable_when_model_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "missing.onnx"))
    with pytest.raises(embedding.EmbeddingUnavailable):
        embedding.embed(Image.new("RGB", (8, 8)))


def test_embed_raises_unavailable_when_model_corrupt(monkeypatch, tmp_path):
    bad = tmp_path / "bad.onnx"
    bad.write_bytes(b"this is not an onnx model")
    monkeypatch.setenv("MODEL_PATH", str(bad))
    assert embedding.available() is True  # 文件在，只是坏的
    with pytest.raises(embedding.EmbeddingUnavailable):
        embedding.embed(Image.new("RGB", (8, 8)))


def test_blob_roundtrip():
    vec = np.arange(embedding.DIM, dtype=np.float32) / 7
    blob = embedding.to_blob(vec)
    assert len(blob) == embedding.DIM * 4
    np.testing.assert_array_equal(embedding.from_blob(blob), vec)


def _pattern(seed):
    rng = np.random.default_rng(seed)
    img = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(img)
    for _ in range(40):
        x, y = rng.integers(0, 750, 2)
        w, h = rng.integers(10, 150, 2)
        draw.rectangle([x, y, x + w, y + h], fill=tuple(int(c) for c in rng.integers(0, 255, 3)))
    return img


REAL_MODEL = os.environ.get("PICLOG_TEST_MODEL", "")


@pytest.mark.model
@pytest.mark.skipif(
    not os.path.isfile(REAL_MODEL),
    reason="设置 PICLOG_TEST_MODEL=<dinov2-small.onnx 路径> 才会运行真实模型冒烟测试",
)
def test_real_model_smoke(monkeypatch):
    monkeypatch.setenv("MODEL_PATH", REAL_MODEL)
    img = _pattern(1)
    vec = embedding.embed(img)
    assert vec.shape == (embedding.DIM,)
    assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-4
    np.testing.assert_array_equal(vec, embedding.embed(img))  # 确定性
    cropped = embedding.embed(img.crop((20, 15, 780, 585)))
    assert float(vec @ cropped) > 0.95
```

在 `backend/tests/conftest.py` 末尾追加 marker 注册（避免 `PytestUnknownMarkWarning`）：

```python
def pytest_configure(config):
    config.addinivalue_line("markers", "model: 需要真实模型文件的测试（默认跳过）")
```

- [ ] **Step 5: 运行测试确认失败**

Run: `cd backend && .venv/bin/pytest tests/test_embedding.py -q`
Expected: 收集失败，`ModuleNotFoundError: No module named 'embedding'`

- [ ] **Step 6: 实现 embedding 模块**

Create `backend/embedding.py`:

```python
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
```

- [ ] **Step 7: 运行测试确认通过**

Run: `cd backend && .venv/bin/pytest tests/test_embedding.py -q`
Expected: 全部通过，`test_real_model_smoke` 显示为 skipped。

- [ ] **Step 8: 用真实模型跑冒烟测试**

（Task 0 已把模型下载到 `~/.cache/piclog/dinov2-small.onnx`）

Run: `cd backend && PICLOG_TEST_MODEL=~/.cache/piclog/dinov2-small.onnx .venv/bin/pytest tests/test_embedding.py -q -m model`
Expected: `1 passed`（其余 deselected）

- [ ] **Step 9: 跑全部测试**

Run: `cd backend && .venv/bin/pytest tests -q`
Expected: 77 个旧测试 + 新测试全部通过，1 skipped。

- [ ] **Step 10: Commit**

```bash
git add backend/requirements.txt backend/embedding.py backend/tests/conftest.py backend/tests/helpers.py backend/tests/test_embedding.py
git commit -m "Add DINOv2 image embedding module

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 向量表与后台索引

**Files:**
- Create: `backend/indexer.py`
- Create: `backend/tests/test_indexer.py`
- Modify: `backend/database.py`（`init_db()` 内，`_init_custom_fields(conn)` 之后）
- Modify: `backend/main.py`（startup）
- Modify: `backend/routers/images.py`（`upload_images` 的 `db.commit()` 之后）
- Modify: `backend/routers/logs.py`（`create_log` 的 `db.commit()` 之后）

**Interfaces:**
- Consumes: `embedding.MODEL_ID`、`embedding.available()`、`embedding.embed()`、`embedding.to_blob()`、`embedding.EmbeddingUnavailable`；fixture `fake_embedder`；`tests.helpers` 的 `solid_image_bytes`、颜色常量
- Produces:
  - 表 `image_embeddings(image_id INTEGER PRIMARY KEY, model TEXT, vector BLOB, created_at)`，`image_id` 外键 `ON DELETE CASCADE`
  - `indexer.process_pending() -> int`（本次写入的向量数）
  - `indexer.count_pending(conn) -> int`
  - `indexer.notify() -> None`、`indexer.start() -> None`、`indexer.reset_state() -> None`

- [ ] **Step 1: 写失败的测试**

Create `backend/tests/test_indexer.py`:

```python
import sqlite3

import numpy as np
import pytest

import database
import embedding
import indexer
from tests.helpers import BLUE, RED, solid_image_bytes


@pytest.fixture(autouse=True)
def clean_indexer_state():
    indexer.reset_state()
    yield
    indexer.reset_state()


@pytest.fixture()
def log_id(client):
    cid = client.post("/api/categories", json={"name": "手套"}).json()["id"]
    return client.post("/api/logs", data={"category_id": cid}).json()["id"]


def upload(client, log_id, *files):
    resp = client.post(f"/api/logs/{log_id}/images", files=[("files", f) for f in files])
    assert resp.status_code == 201, resp.text
    return resp.json()


def png(name, color):
    return (name, solid_image_bytes(color), "image/png")


def embedding_rows(db_conn):
    return db_conn.execute("SELECT image_id, model, vector FROM image_embeddings ORDER BY image_id").fetchall()


def test_process_pending_writes_vectors_for_uploaded_images(client, fake_embedder, log_id, db_conn):
    images = upload(client, log_id, png("a.png", RED), png("b.png", BLUE))
    assert indexer.process_pending() == 2

    rows = embedding_rows(db_conn)
    assert sorted(r["image_id"] for r in rows) == sorted(i["id"] for i in images)
    for r in rows:
        assert r["model"] == embedding.MODEL_ID
        vec = embedding.from_blob(r["vector"])
        assert vec.shape == (embedding.DIM,)
        assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-5


def test_process_pending_is_idempotent(client, fake_embedder, log_id):
    upload(client, log_id, png("a.png", RED))
    assert indexer.process_pending() == 1
    assert indexer.process_pending() == 0


def test_images_created_with_log_are_indexed(client, fake_embedder):
    cid = client.post("/api/categories", json={"name": "手套"}).json()["id"]
    resp = client.post("/api/logs", data={"category_id": cid}, files=[("files", png("a.png", RED))])
    assert resp.status_code == 201
    assert indexer.process_pending() == 1


def test_deleting_image_cascades_to_embedding(client, fake_embedder, log_id, db_conn):
    [image] = upload(client, log_id, png("a.png", RED))
    indexer.process_pending()
    assert client.delete(f"/api/images/{image['id']}").status_code == 204
    assert embedding_rows(db_conn) == []


def test_vectors_from_another_model_count_as_pending(client, fake_embedder, log_id, db_conn):
    upload(client, log_id, png("a.png", RED))
    indexer.process_pending()
    db_conn.execute("UPDATE image_embeddings SET model = 'old-model'")
    db_conn.commit()

    assert indexer.count_pending(db_conn) == 1
    assert indexer.process_pending() == 1
    assert [r["model"] for r in embedding_rows(db_conn)] == [embedding.MODEL_ID]
    assert indexer.count_pending(db_conn) == 0


def test_soft_deleted_logs_are_not_indexed(client, fake_embedder, log_id, db_conn):
    upload(client, log_id, png("a.png", RED))
    assert client.delete(f"/api/logs/{log_id}").status_code == 204
    assert indexer.count_pending(db_conn) == 0
    assert indexer.process_pending() == 0


def test_non_image_file_is_skipped_and_not_counted_as_pending(client, fake_embedder, log_id, db_conn):
    upload(client, log_id, ("notes.txt", b"just some text", "text/plain"))
    assert indexer.count_pending(db_conn) == 1  # 还没试过
    assert indexer.process_pending() == 0
    assert indexer.count_pending(db_conn) == 0  # 试过、解码失败，不再算待处理
    assert embedding_rows(db_conn) == []


def test_image_deleted_during_inference_is_not_written(client, log_id, db_conn):
    [image] = upload(client, log_id, png("a.png", RED))

    def embed_then_delete(img):
        # 模拟推理的几秒钟里，用户在别的请求里删掉了这张图
        other = sqlite3.connect(database.DB_PATH)
        other.execute("PRAGMA foreign_keys=ON")
        other.execute("DELETE FROM images WHERE id = ?", (image["id"],))
        other.commit()
        other.close()
        return np.ones(embedding.DIM, dtype=np.float32)

    embedding.set_embedder(embed_then_delete)
    try:
        assert indexer.process_pending() == 0  # 不抛异常
    finally:
        embedding.set_embedder(None)
    assert embedding_rows(db_conn) == []


def test_process_pending_without_model_does_nothing(client, log_id, db_conn):
    upload(client, log_id, png("a.png", RED))
    assert indexer.process_pending() == 0
    assert indexer.count_pending(db_conn) == 1


def test_upload_still_works_without_model(client, log_id):
    [image] = upload(client, log_id, png("a.png", RED))
    assert image["log_id"] == log_id
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/pytest tests/test_indexer.py -q`
Expected: 收集失败，`ModuleNotFoundError: No module named 'indexer'`

- [ ] **Step 3: 建表**

在 `backend/database.py` 的 `init_db()` 里，`_init_custom_fields(conn)` 下一行加 `_init_image_embeddings(conn)`，并在 `_init_custom_fields` 函数定义之后新增：

```python
def _init_image_embeddings(conn):
    # 以图搜图的特征向量，一张图一行。model 与当前模型不一致的行视为待补算
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS image_embeddings (
            image_id   INTEGER PRIMARY KEY,
            model      TEXT NOT NULL,
            vector     BLOB NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
        );
    """)
```

- [ ] **Step 4: 实现 indexer**

Create `backend/indexer.py`:

```python
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
```

- [ ] **Step 5: 接入上传与启动**

`backend/routers/images.py`：顶部 import 区加 `import indexer`；`upload_images` 里 `db.commit()` 的下一行加：

```python
    indexer.notify()
```

`backend/routers/logs.py`：顶部 import 区加 `import indexer`；`create_log` 里 `db.commit()`（`except HTTPException` 块之后那一个）的下一行加：

```python
    indexer.notify()
```

`backend/main.py`：import 区加 `import indexer`；`startup()` 改为：

```python
@app.on_event("startup")
def startup():
    init_db()
    migrate_existing()
    indexer.start()
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && .venv/bin/pytest tests/test_indexer.py -q`
Expected: 全部通过。

- [ ] **Step 7: 跑全部测试**

Run: `cd backend && .venv/bin/pytest tests -q`
Expected: 全部通过，1 skipped。

- [ ] **Step 8: Commit**

```bash
git add backend/database.py backend/indexer.py backend/main.py backend/routers/images.py backend/routers/logs.py backend/tests/test_indexer.py
git commit -m "Index image embeddings in a background thread

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 搜索接口

**Files:**
- Create: `backend/image_search.py`
- Create: `backend/routers/search.py`
- Create: `backend/tests/test_image_search.py`
- Modify: `backend/models.py`（末尾追加）
- Modify: `backend/main.py`（注册路由）

**Interfaces:**
- Consumes: `embedding.*`（Task 1）；`indexer.process_pending()`、`indexer.count_pending(conn)`、`indexer.reset_state()`（Task 2）；`routers.logs.LOG_COLUMNS`、`routers.logs._build_log_list(db, rows)`（已有）
- Produces:
  - `image_search.MIN_SCORE: float`、`image_search.Hit(NamedTuple: log_id, score, image_id)`
  - `image_search.rank_logs(db, query_vec, limit, min_score=MIN_SCORE) -> tuple[list[Hit], int]`
  - `POST /api/search/image`（multipart 字段 `file`；query `limit`、`min_score`）→ `{"items": [{"log": LogOut, "score": float, "matched_image": ImageOut}], "indexed": int, "pending": int}`
  - 错误：503 `"以图搜图未启用"`、400 `"无法识别的图片"`、400 `"图片尺寸过大"`

- [ ] **Step 1: 写失败的测试**

Create `backend/tests/test_image_search.py`:

```python
import io
import sqlite3

import numpy as np
import pytest
from PIL import Image

import embedding
import indexer
from tests.helpers import BLUE, GREEN, PURPLE, RED, mean_color_vector, solid_image_bytes


@pytest.fixture(autouse=True)
def clean_indexer_state():
    indexer.reset_state()
    yield
    indexer.reset_state()


def png(name, color, size=(32, 32)):
    return (name, solid_image_bytes(color, size), "image/png")


def make_log(client, cid, description, *files):
    resp = client.post(
        "/api/logs",
        data={"category_id": cid, "description": description},
        files=[("files", f) for f in files],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def gallery(client, fake_embedder):
    """红日志（红图 + 蓝图）、紫日志、蓝日志、绿日志；全部建好索引。"""
    cid = client.post("/api/categories", json={"name": "手套"}).json()["id"]
    logs = {
        "red": make_log(client, cid, "红手套", png("r.png", RED), png("rb.png", BLUE)),
        "purple": make_log(client, cid, "紫手套", png("p.png", PURPLE)),
        "blue": make_log(client, cid, "蓝手套", png("b.png", BLUE)),
        "green": make_log(client, cid, "绿手套", png("g.png", GREEN)),
    }
    assert indexer.process_pending() == 5
    logs["cid"] = cid
    return logs


def search(client, content, **params):
    return client.post(
        "/api/search/image", params=params, files={"file": ("q.jpg", content, "image/jpeg")}
    )


def test_returns_matching_logs_sorted_and_drops_low_scores(client, gallery):
    resp = search(client, solid_image_bytes(RED))
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    # 红 ≈ 1、紫 ≈ 0.707；蓝、绿 ≈ 0 低于 MIN_SCORE 被丢弃
    assert [it["log"]["id"] for it in items] == [gallery["red"]["id"], gallery["purple"]["id"]]
    assert items[0]["score"] > 0.99
    assert 0.6 < items[1]["score"] < 0.8


def test_each_log_appears_once_with_its_best_image(client, gallery):
    items = search(client, solid_image_bytes(BLUE)).json()["items"]
    ids = [it["log"]["id"] for it in items]
    assert sorted(ids) == sorted({gallery["red"]["id"], gallery["blue"]["id"], gallery["purple"]["id"]})
    red_hit = next(it for it in items if it["log"]["id"] == gallery["red"]["id"])
    blue_image = gallery["red"]["images"][1]  # 红日志里的那张蓝图
    assert red_hit["matched_image"]["id"] == blue_image["id"]
    assert red_hit["score"] > 0.99


def test_hit_carries_full_log_payload(client, gallery):
    hit = search(client, solid_image_bytes(RED)).json()["items"][0]
    assert hit["log"]["description"] == "红手套"
    assert hit["log"]["category_name"] == "手套"
    assert len(hit["log"]["images"]) == 2
    assert "field_values" in hit["log"]


def test_limit(client, gallery):
    items = search(client, solid_image_bytes(RED), limit=1).json()["items"]
    assert len(items) == 1


@pytest.mark.parametrize("limit", [0, 51])
def test_limit_out_of_range_is_rejected(client, gallery, limit):
    assert search(client, solid_image_bytes(RED), limit=limit).status_code == 422


def test_min_score_minus_one_returns_everything(client, gallery):
    items = search(client, solid_image_bytes(RED), min_score=-1).json()["items"]
    assert len(items) == 4


def test_soft_deleted_logs_are_excluded(client, gallery):
    client.delete(f"/api/logs/{gallery['red']['id']}")
    ids = [it["log"]["id"] for it in search(client, solid_image_bytes(RED)).json()["items"]]
    assert gallery["red"]["id"] not in ids


def test_indexed_and_pending_counts(client, gallery):
    body = search(client, solid_image_bytes(RED)).json()
    assert body["indexed"] == 5
    assert body["pending"] == 0

    make_log(client, gallery["cid"], "新的", png("n.png", RED))
    body = search(client, solid_image_bytes(RED)).json()
    assert body["indexed"] == 5
    assert body["pending"] == 1


def test_empty_index_returns_pending_count(client, fake_embedder):
    cid = client.post("/api/categories", json={"name": "手套"}).json()["id"]
    make_log(client, cid, "a", png("a.png", RED))
    make_log(client, cid, "b", png("b.png", BLUE))
    resp = search(client, solid_image_bytes(RED))
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "indexed": 0, "pending": 2}


def test_returns_503_without_model(client):
    resp = search(client, solid_image_bytes(RED))
    assert resp.status_code == 503
    assert resp.json()["detail"] == "以图搜图未启用"


def test_returns_503_when_model_file_is_corrupt(client, monkeypatch, tmp_path):
    bad = tmp_path / "bad.onnx"
    bad.write_bytes(b"not a model")
    monkeypatch.setenv("MODEL_PATH", str(bad))
    embedding._session = None
    resp = search(client, solid_image_bytes(RED))
    assert resp.status_code == 503
    assert resp.json()["detail"] == "以图搜图未启用"


def test_non_image_returns_400(client, fake_embedder):
    resp = search(client, b"definitely not an image")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "无法识别的图片"


def test_truncated_jpeg_returns_400(client, fake_embedder):
    full = solid_image_bytes(RED, size=(200, 200), fmt="JPEG")
    resp = search(client, full[: len(full) // 2])
    assert resp.status_code == 400
    assert resp.json()["detail"] == "无法识别的图片"


def test_oversized_image_returns_400(client, fake_embedder, monkeypatch):
    # 超过 2 倍 MAX_IMAGE_PIXELS 时 Pillow 抛 DecompressionBombError
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    resp = search(client, solid_image_bytes(RED, size=(100, 100)))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "图片尺寸过大"


@pytest.fixture()
def seen_sizes():
    sizes = []

    def recording(img):
        sizes.append(img.size)
        return mean_color_vector(img)

    embedding.set_embedder(recording)
    yield sizes
    embedding.set_embedder(None)


def test_exif_orientation_is_applied(client, seen_sizes):
    # 40×20 的横图，EXIF 标记「顺时针转 90°」：摆正后应是 20×40 的竖图
    exif = Image.Exif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), RED).save(buf, "JPEG", exif=exif.tobytes())
    assert search(client, buf.getvalue()).status_code == 200
    assert seen_sizes == [(20, 40)]


def test_query_image_is_downscaled_to_800(client, seen_sizes):
    assert search(client, solid_image_bytes(RED, size=(2000, 1000))).status_code == 200
    assert seen_sizes == [(800, 400)]


def test_rgba_query_image_is_accepted(client, seen_sizes):
    buf = io.BytesIO()
    Image.new("RGBA", (20, 20), (255, 0, 0, 128)).save(buf, "PNG")
    assert search(client, buf.getvalue()).status_code == 200


def test_constant_number_of_queries(client, gallery):
    """回归护栏：SQL 语句数不随命中条数增长（同 test_log_filter_sort 的做法）。"""
    import database
    from main import app

    statements = []

    def tracing_db():
        conn = sqlite3.connect(database.DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.set_trace_callback(statements.append)
        try:
            yield conn
        finally:
            conn.close()

    def run(min_score):
        statements.clear()
        app.dependency_overrides[database.get_db] = tracing_db
        try:
            resp = search(client, solid_image_bytes(RED), min_score=min_score)
        finally:
            app.dependency_overrides.pop(database.get_db, None)
        return len(resp.json()["items"]), len(statements)

    few_hits, few_statements = run(0.9)    # 只命中红日志
    many_hits, many_statements = run(-1)   # 命中全部 4 条
    assert few_hits == 1 and many_hits == 4
    assert few_statements == many_statements
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/pytest tests/test_image_search.py -q`
Expected: 大多数测试 FAIL，状态码 404（路由不存在）。

- [ ] **Step 3: 响应模型**

`backend/models.py` 末尾追加：

```python
class ImageSearchHit(BaseModel):
    log: LogOut
    score: float
    matched_image: ImageOut


class ImageSearchOut(BaseModel):
    items: list[ImageSearchHit]
    indexed: int   # 参与比对的向量数
    pending: int   # 还没建好索引的图片数
```

- [ ] **Step 4: 排序逻辑**

Create `backend/image_search.py`:

```python
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
```

- [ ] **Step 5: 路由**

Create `backend/routers/search.py`:

```python
"""拍照以图搜图。"""
import io
import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

import embedding
import indexer
from database import get_db
from image_search import MIN_SCORE, rank_logs
from models import ImageSearchOut
from routers.logs import LOG_COLUMNS, _build_log_list

router = APIRouter(tags=["search"])

# 与缩略图尺寸一致：索引就是用 800px 缩略图算的
QUERY_MAX_SIZE = (800, 800)


def _load_query_image(content: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(content))
        img.load()
    except Image.DecompressionBombError:
        # 不是 OSError 的子类，必须单独捕获
        raise HTTPException(400, "图片尺寸过大")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "无法识别的图片")
    # 手机竖拍的照片像素是横的，靠 EXIF 标记方向；不摆正就和库里的图对不上
    img = ImageOps.exif_transpose(img)
    img.thumbnail(QUERY_MAX_SIZE)
    return img.convert("RGB")


# 同步函数：FastAPI 会放到线程池里跑，几秒的推理不会卡住事件循环
@router.post("/api/search/image", response_model=ImageSearchOut)
def search_by_image(
    file: UploadFile = File(...),
    limit: int = Query(20, ge=1, le=50),
    # 评测脚本传 -1 取回全部分数；前端不传
    min_score: float = Query(MIN_SCORE, ge=-1.0, le=1.0),
    db: sqlite3.Connection = Depends(get_db),
):
    if not embedding.available():
        raise HTTPException(503, "以图搜图未启用")
    query_img = _load_query_image(file.file.read())
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

    return {"items": items, "indexed": indexed, "pending": indexer.count_pending(db)}
```

`backend/main.py`：`from routers import categories, logs, images, fields` 改为 `from routers import categories, logs, images, fields, search`，并在 `app.include_router(fields.router)` 下一行加 `app.include_router(search.router)`。

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && .venv/bin/pytest tests/test_image_search.py -q`
Expected: 全部通过。

- [ ] **Step 7: 跑全部测试**

Run: `cd backend && .venv/bin/pytest tests -q`
Expected: 全部通过，1 skipped。

- [ ] **Step 8: Commit**

```bash
git add backend/image_search.py backend/routers/search.py backend/models.py backend/main.py backend/tests/test_image_search.py
git commit -m "Add image search endpoint

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 模型下载脚本与评测脚本

**Files:**
- Create: `scripts/fetch-model.sh`
- Create: `scripts/eval-search.py`
- Modify: `docker-compose.yml`
- Modify: `scripts/setup-dev.sh`（末尾说明文字）

**Interfaces:**
- Consumes: `POST /api/search/image`（Task 3），`min_score=-1`
- Produces: `./scripts/fetch-model.sh [--local]`；`backend/.venv/bin/python scripts/eval-search.py <目录> [--url URL]`

- [ ] **Step 1: 模型下载脚本**

Create `scripts/fetch-model.sh`:

```bash
#!/usr/bin/env bash
#
# 下载以图搜图的模型（DINOv2-small ONNX），校验后放到 NAS 的 data/models/ 下并重启容器。
#
#   ./scripts/fetch-model.sh           下载 → 校验 → 上传到 NAS → 重启容器
#   ./scripts/fetch-model.sh --local   只放到 backend/devdata/models/（本地开发用）
#
# 下载在本机进行（NAS 不一定能访问 HuggingFace）。国内网络可以先
#   export HF_ENDPOINT=https://hf-mirror.com
# 已下载且校验通过的文件会复用，重复运行是安全的。
#
set -euo pipefail

NAS_HOST="${PICLOG_NAS_HOST:-root@192.168.8.10}"
NAS_DIR="${PICLOG_NAS_DIR:-/volume2/homes/darlingz/pic}"
NAS_COMPOSE="${PICLOG_NAS_COMPOSE:-/usr/local/bin/docker-compose}"
NAS_SERVICE="${PICLOG_NAS_SERVICE:-piclog}"
HF_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}"

MODEL_URL_PATH="onnx-community/dinov2-small/resolve/main/onnx/model.onnx"
MODEL_NAME="dinov2-small.onnx"
MODEL_SHA256="f22797eabf810a75e41de68d378541ebea372122b25c4ce3ef25ff618250c20a"

SSH_OPTS=(-o ConnectTimeout=15 -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
REMOTE_PATH="/usr/local/bin:/usr/bin:/bin"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/piclog"
CACHED="$CACHE_DIR/$MODEL_NAME"

die() { printf '✗ %s\n' "$*" >&2; exit 1; }
sha_of() { shasum -a 256 "$1" | cut -d' ' -f1; }
nas() { ssh "${SSH_OPTS[@]}" "$NAS_HOST" "export PATH=${REMOTE_PATH}:\$PATH; $*"; }

# ------------------------------------------------------------------ 下载
mkdir -p "$CACHE_DIR"
if [ -f "$CACHED" ] && [ "$(sha_of "$CACHED")" = "$MODEL_SHA256" ]; then
    echo "✓ 使用已缓存的模型 $CACHED"
else
    echo "▶ 下载 $HF_ENDPOINT/$MODEL_URL_PATH（约 85MB）"
    curl -fL --retry 3 -o "$CACHED.part" "$HF_ENDPOINT/$MODEL_URL_PATH"
    actual="$(sha_of "$CACHED.part")"
    if [ "$actual" != "$MODEL_SHA256" ]; then
        rm -f "$CACHED.part"
        die "sha256 不匹配：期望 $MODEL_SHA256，实际 $actual"
    fi
    mv "$CACHED.part" "$CACHED"
    echo "✓ 下载完成，校验通过"
fi

# ------------------------------------------------------------------ 本地开发
if [ "${1:-}" = "--local" ]; then
    dest="$REPO_ROOT/backend/devdata/models"
    mkdir -p "$dest"
    cp "$CACHED" "$dest/$MODEL_NAME"
    echo "✓ 已放到 $dest/$MODEL_NAME"
    echo "  启动后端时加上 MODEL_PATH=./devdata/models/$MODEL_NAME"
    exit 0
fi

# ------------------------------------------------------------------ 上传到 NAS
remote_dir="$NAS_DIR/data/models"
remote_file="$remote_dir/$MODEL_NAME"
remote_sha="$(nas "sha256sum '$remote_file' 2>/dev/null | cut -d' ' -f1" || true)"
if [ "$remote_sha" = "$MODEL_SHA256" ]; then
    echo "✓ NAS 上已有同一个模型文件，跳过上传"
else
    echo "▶ 上传到 $NAS_HOST:$remote_file"
    # 用 ssh + cat 而不是 scp：群晖默认不一定开启 SFTP 子系统
    ssh "${SSH_OPTS[@]}" "$NAS_HOST" \
        "mkdir -p '$remote_dir' && cat > '$remote_file.part' && mv '$remote_file.part' '$remote_file'" \
        < "$CACHED"
    remote_sha="$(nas "sha256sum '$remote_file' | cut -d' ' -f1")"
    [ "$remote_sha" = "$MODEL_SHA256" ] || die "上传后 NAS 上的文件校验不通过：$remote_sha"
    echo "✓ 上传完成，校验通过"
fi

# ------------------------------------------------------------------ 重启
echo "▶ 重启容器以启用以图搜图"
nas "cd '$NAS_DIR' && '$NAS_COMPOSE' restart '$NAS_SERVICE'"
echo "✓ 完成。后台会开始为已有图片建立索引（每张约 1–3 秒）"
```

Run: `chmod +x scripts/fetch-model.sh && bash -n scripts/fetch-model.sh`
Expected: 无输出（语法正确）。

- [ ] **Step 2: 本地放置模型**

Run: `./scripts/fetch-model.sh --local`
Expected: `✓ 使用已缓存的模型 …`（Task 0 已下载）和 `✓ 已放到 …/backend/devdata/models/dinov2-small.onnx`

- [ ] **Step 3: 评测脚本**

Create `scripts/eval-search.py`:

```python
#!/usr/bin/env python3
"""用真实照片评测以图搜图，帮助确定相似度阈值。

用法：
    backend/.venv/bin/python scripts/eval-search.py <照片目录> [--url http://192.168.8.10:8080]

照片文件名以「正确答案」的日志 id 开头，如 37_a.jpg、37_side.jpg（请用 JPEG/PNG，
服务端不支持 HEIC）。脚本逐张调用搜索接口（min_score=-1，取回全部分数），输出：
  - 正确日志的排名：第 1 / 前 3 / 更靠后 / 不在前 50
  - 正确匹配的分数、每张照片「排第一的错误匹配」的分数
据此调整 backend/image_search.py 的 MIN_SCORE
和 frontend/src/imageSearch.js 的 SCORE_LEVELS。
"""
import argparse
import re
import statistics
import sys
from pathlib import Path

import httpx

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def expected_log_id(path: Path):
    m = re.match(r"(\d+)_", path.name)
    return int(m.group(1)) if m else None


def describe(label, values):
    if not values:
        print(f"  {label}: 无")
        return
    q = sorted(values)
    print(
        f"  {label}: n={len(q)}  最小 {q[0]:.3f}  中位数 {statistics.median(q):.3f}  最大 {q[-1]:.3f}"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", type=Path)
    ap.add_argument("--url", default="http://192.168.8.10:8080")
    args = ap.parse_args()
    base = args.url.rstrip("/")

    photos = sorted(p for p in args.dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not photos:
        sys.exit(f"{args.dir} 里没有 JPEG/PNG/WebP 照片")

    ranks = {"第 1": 0, "前 3": 0, "更靠后": 0, "不在前 50": 0}
    correct_scores, wrong_top_scores = [], []
    pending = 0

    with httpx.Client(timeout=120) as client:
        for p in photos:
            expected = expected_log_id(p)
            if expected is None:
                print(f"跳过 {p.name}：文件名不是以「日志id_」开头")
                continue
            with p.open("rb") as f:
                resp = client.post(
                    f"{base}/api/search/image",
                    params={"limit": 50, "min_score": -1},
                    files={"file": (p.name, f, "application/octet-stream")},
                )
            if resp.status_code != 200:
                print(f"{p.name}: 请求失败 {resp.status_code} {resp.text}")
                continue
            data = resp.json()
            pending = data["pending"]
            items = data["items"]
            ids = [it["log"]["id"] for it in items]
            wrong = [it["score"] for it in items if it["log"]["id"] != expected]
            if wrong:
                wrong_top_scores.append(wrong[0])
            first = f"#{ids[0]}（{items[0]['score']:.3f}）" if items else "无"

            if expected in ids:
                rank = ids.index(expected) + 1
                score = items[rank - 1]["score"]
                correct_scores.append(score)
                ranks["第 1" if rank == 1 else "前 3" if rank <= 3 else "更靠后"] += 1
                print(f"{p.name}: 正确日志 #{expected} 排第 {rank}，分数 {score:.3f}；第一名 {first}")
            else:
                ranks["不在前 50"] += 1
                print(f"{p.name}: 正确日志 #{expected} 不在前 50；第一名 {first}")

    total = sum(ranks.values())
    print(f"\n共 {total} 张")
    for k, v in ranks.items():
        print(f"  {k}: {v}（{v / total:.0%}）" if total else f"  {k}: {v}")
    print("分数分布：")
    describe("正确匹配", correct_scores)
    describe("排第一的错误匹配", wrong_top_scores)
    if pending:
        print(f"\n注意：还有 {pending} 张图片没建好索引，结果可能偏低")
    print(
        "\n建议：MIN_SCORE 取略低于「正确匹配」的最小值；"
        "「很可能是同一件」的门槛取高于大多数「排第一的错误匹配」的值。"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 用本地开发服务器 + 真实模型跑通**

终端 A 启动后端（使用独立的临时库，不碰 devdata 里已有数据）：

```bash
cd backend && rm -rf /tmp/piclog-eval && mkdir -p /tmp/piclog-eval && \
  DB_PATH=/tmp/piclog-eval/piclog.db UPLOAD_DIR=/tmp/piclog-eval/uploads \
  MODEL_PATH=./devdata/models/dinov2-small.onnx \
  .venv/bin/python -m uvicorn main:app --port 8765
```

终端 B 造两条日志和评测照片，然后跑脚本：

```bash
cd backend && .venv/bin/python - <<'EOF'
import io, time, httpx, numpy as np
from pathlib import Path
from PIL import Image, ImageDraw

def pattern(seed):
    rng = np.random.default_rng(seed)
    img = Image.new("RGB", (800, 600), "white"); d = ImageDraw.Draw(img)
    for _ in range(40):
        x, y = rng.integers(0, 750, 2); w, h = rng.integers(10, 150, 2)
        d.rectangle([x, y, x + w, y + h], fill=tuple(int(c) for c in rng.integers(0, 255, 3)))
    return img

def jpg(img):
    b = io.BytesIO(); img.save(b, "JPEG"); return b.getvalue()

c = httpx.Client(base_url="http://127.0.0.1:8765", timeout=60)
cid = c.post("/api/categories", json={"name": "测试"}).json()["id"]
out = Path("/tmp/piclog-eval/queries"); out.mkdir(exist_ok=True)
for seed in (1, 2):
    log = c.post("/api/logs", data={"category_id": cid, "description": f"图案{seed}"},
                 files=[("files", (f"{seed}.jpg", jpg(pattern(seed)), "image/jpeg"))]).json()
    pattern(seed).crop((20, 15, 780, 585)).save(out / f"{log['id']}_crop.jpg")
time.sleep(3)  # 等后台线程建好索引
print("ok")
EOF
backend/.venv/bin/python scripts/eval-search.py /tmp/piclog-eval/queries --url http://127.0.0.1:8765
```

Expected: 两张照片都显示「排第 1」，汇总里「第 1: 2（100%）」，没有 `pending` 提示。然后停掉终端 A 的服务器，`rm -rf /tmp/piclog-eval`。

- [ ] **Step 5: compose 与开发说明**

`docker-compose.yml` 的 `environment:` 列表末尾加一行：

```yaml
      - MODEL_PATH=/app/data/models/dinov2-small.onnx
```

`scripts/setup-dev.sh` 末尾 heredoc 中，把「本地起开发环境」的终端 1 命令改为带模型路径，并补充模型说明：

```
本地起开发环境：
  终端 1  cd backend && DB_PATH=./devdata/piclog.db UPLOAD_DIR=./devuploads \
            MODEL_PATH=./devdata/models/dinov2-small.onnx \
            .venv/bin/python -m uvicorn main:app --reload --port 8080
  终端 2  cd frontend && npm run dev

以图搜图的模型（约 85MB，不在 git 里）：
  ./scripts/fetch-model.sh --local   放到本地开发目录
  ./scripts/fetch-model.sh           上传到 NAS 并重启容器（首次上线时跑一次）
```

- [ ] **Step 6: Commit**

```bash
git add scripts/fetch-model.sh scripts/eval-search.py docker-compose.yml scripts/setup-dev.sh
git commit -m "Add model fetch and search evaluation scripts

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 抽出 LogCard 组件（纯重构）

搜索结果卡片与列表卡片几乎一样，只是封面图要用「匹配到的那张」、左上角多一个相似度标签。先把卡片抽成组件，列表页行为不变。

**Files:**
- Create: `frontend/src/components/LogCard.vue`
- Modify: `frontend/src/views/LogList.vue`（卡片 `<router-link>` 块、`formatDate`、`cardValue`）

**Interfaces:**
- Consumes: `StatusBadge.vue`（已有）
- Produces: `<LogCard :log="log" :image="image?">`，`image` 省略时用 `log.images[0]`；具名插槽 `badge` 渲染在封面图容器内（容器是 `relative`）

- [ ] **Step 1: 新建组件**

Create `frontend/src/components/LogCard.vue`（模板内容从 `LogList.vue` 原样搬过来，只把封面图改成 `cover`、加 `badge` 插槽）：

```vue
<template>
  <router-link
    :to="`/logs/${log.id}`"
    class="mb-3 block break-inside-avoid rounded-2xl border border-slate-100 bg-white p-3 shadow-sm transition-shadow hover:shadow-md"
  >
    <!-- Cover image -->
    <div v-if="cover" class="relative mb-2 overflow-hidden rounded-xl bg-slate-50">
      <img
        :src="`/uploads/thumbs/${cover.filename}`"
        :alt="cover.original_name"
        class="w-full rounded-xl"
      />
      <span
        v-if="log.images.length > 1"
        class="absolute right-1.5 top-1.5 rounded-full bg-black/50 px-1.5 py-0.5 text-[10px] font-medium text-white"
      >
        {{ log.images.length }}张
      </span>
      <slot name="badge" />
    </div>

    <!-- Tags row -->
    <div class="mb-1.5 flex items-center gap-1.5">
      <span class="inline-flex items-center rounded-md bg-primary-50 px-1.5 py-0.5 text-[10px] font-medium text-primary-600">
        {{ log.category_name }}
      </span>
      <StatusBadge :status="log.status" />
    </div>

    <!-- Description -->
    <p v-if="log.description" class="mb-1.5 line-clamp-2 text-xs text-slate-700">
      {{ log.description }}
    </p>

    <!-- Custom fields on card -->
    <div v-if="log.field_values && log.field_values.length" class="mb-1.5 space-y-0.5">
      <div
        v-for="fv in log.field_values"
        :key="fv.field_id"
        class="flex items-baseline gap-1.5 text-[10px] leading-tight"
      >
        <span class="shrink-0 text-slate-400">{{ fv.name }}</span>
        <span class="min-w-0 flex-1 truncate text-slate-600">{{ cardValue(fv) }}</span>
      </div>
    </div>

    <!-- Date -->
    <div class="text-[10px] text-slate-400">
      {{ formatDate(log.created_at) }}
    </div>
  </router-link>
</template>

<script setup>
import { computed } from 'vue'
import StatusBadge from './StatusBadge.vue'

const props = defineProps({
  log: { type: Object, required: true },
  // 封面图；不传就用日志的第一张图。搜索结果传「匹配到的那张」
  image: { type: Object, default: null },
})

const cover = computed(() => props.image || props.log.images[0] || null)

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleString('zh-CN')
}

function cardValue(fv) {
  if (fv.type === 'select') {
    return fv.option_labels[0] || ''
  }
  if (fv.type === 'multiselect') {
    const labels = fv.option_labels || []
    if (labels.length <= 2) return labels.join('、')
    return `${labels.slice(0, 2).join('、')} +${labels.length - 2}`
  }
  return fv.value
}
</script>
```

- [ ] **Step 2: 列表页改用组件**

在 `frontend/src/views/LogList.vue` 中：

1. 把 `<!-- Log cards — masonry -->` 下 `<div class="columns-2 gap-3">` 里的整个 `<router-link v-for="log in logs" …>…</router-link>` 块替换为：

```vue
        <LogCard v-for="log in logs" :key="log.id" :log="log" />
```

2. `<script setup>` 的 import 区加 `import LogCard from '../components/LogCard.vue'`
3. 删除 `function formatDate(dt) {…}` 和 `function cardValue(fv) {…}`
4. 检查 `StatusBadge` 在 LogList 模板里是否还有其他用处：

Run: `grep -n "StatusBadge\|formatDate\|cardValue" frontend/src/views/LogList.vue`
Expected: 只剩 `import StatusBadge …` 一行（没有模板用处）→ 删掉这行 import。若还有其他用处则保留。

- [ ] **Step 3: 构建确认**

Run: `cd frontend && npm run build`
Expected: 构建成功，无报错。

- [ ] **Step 4: 目测列表页不变**

启动本地开发环境（`scripts/setup-dev.sh` 末尾的两条命令），浏览器打开 `http://localhost:5173/`：卡片的封面、多图角标、分类标签、状态、描述、自定义字段、日期与改动前一致，点击进入详情正常。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/LogCard.vue frontend/src/views/LogList.vue
git commit -m "Extract LogCard component from the log list

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 前端搜索页与入口

**Files:**
- Modify: `frontend/src/api.js`（`request()` 抛错处；`api` 对象末尾）
- Modify: `frontend/src/imageCompress.js`
- Create: `frontend/src/imageSearch.js`
- Create: `frontend/src/components/CameraSearchButton.vue`
- Create: `frontend/src/views/ImageSearch.vue`
- Modify: `frontend/src/router.js`
- Modify: `frontend/src/views/LogList.vue`（搜索栏）

**Interfaces:**
- Consumes: `POST /api/search/image`（Task 3）；`LogCard`（Task 5）；`PageHeader`、`EmptyState`（已有）
- Produces:
  - `api.searchByImage(file, limit = 20)`；`request()` 抛出的 Error 带 `status`
  - `shrinkForSearch(file) -> Promise<File>`
  - `imageSearch`（reactive：`status`、`previewUrl`、`items`、`indexed`、`pending`、`error`、`errorStatus`）、`searchByPhoto(file)`、`retry()`、`scoreLabel(score) -> { text, cls }`、`SCORE_LEVELS`
  - `<CameraSearchButton variant="icon|primary|ghost" label?>`
  - 路由 `{ path: '/search/image', name: 'ImageSearch' }`

- [ ] **Step 1: api.js**

`request()` 里把

```js
    throw new Error(formatDetail(err.detail) || 'Request failed')
```

替换为：

```js
    const error = new Error(formatDetail(err.detail) || 'Request failed')
    // 调用方有时要按状态码区分（比如以图搜图的 503 = 功能未启用）
    error.status = res.status
    throw error
```

`api` 对象末尾（`deleteImage` 之后）加：

```js

  // Image search
  searchByImage: (file, limit = 20) => {
    const fd = new FormData()
    fd.append('file', file)
    return request(`/api/search/image?limit=${limit}`, { method: 'POST', body: fd })
  },
```

- [ ] **Step 2: imageCompress.js**

把 `async function doCompress(file) {` 改为：

```js
async function doCompress(file, maxEdge = MAX_EDGE, skipBelowBytes = SKIP_BELOW_BYTES) {
```

函数体内把 `MAX_EDGE` 改为 `maxEdge`、`SKIP_BELOW_BYTES` 改为 `skipBelowBytes`（各一处）。

在 `compressImages` 函数之后加：

```js
// 以图搜图用：服务端只用到 800px，缩到 1024 足够，上传也快。
// 不走 cache（与上传用的压缩结果尺寸不同），也不看压缩开关
const SEARCH_MAX_EDGE = 1024

export function shrinkForSearch(file) {
  const job = queue.then(() => doCompress(file, SEARCH_MAX_EDGE, 0))
  queue = job.catch(() => {})
  return job
}
```

- [ ] **Step 3: 搜索状态 store**

Create `frontend/src/imageSearch.js`:

```js
// 以图搜图的状态放在模块里而不是页面组件里：
// 从结果点进详情再返回时，页面重新挂载，结果还在，不用重新识别。
import { reactive } from 'vue'
import { api } from './api.js'
import { shrinkForSearch } from './imageCompress.js'

export const imageSearch = reactive({
  status: 'idle', // idle | loading | done | error
  previewUrl: '',
  items: [],
  indexed: 0,
  pending: 0,
  error: '',
  errorStatus: 0,
})

let lastFile = null
// 连续拍了两张时，只采用最后一次请求的结果
let latest = 0

export async function searchByPhoto(file) {
  lastFile = file
  const token = ++latest
  if (imageSearch.previewUrl) URL.revokeObjectURL(imageSearch.previewUrl)
  Object.assign(imageSearch, {
    status: 'loading',
    previewUrl: URL.createObjectURL(file),
    items: [],
    error: '',
    errorStatus: 0,
  })
  try {
    const small = await shrinkForSearch(file)
    const data = await api.searchByImage(small)
    if (token !== latest) return
    Object.assign(imageSearch, {
      status: 'done',
      items: data.items,
      indexed: data.indexed,
      pending: data.pending,
    })
  } catch (e) {
    if (token !== latest) return
    Object.assign(imageSearch, { status: 'error', error: e.message, errorStatus: e.status || 0 })
  }
}

export function retry() {
  if (lastFile) searchByPhoto(lastFile)
}

// 相似度档位。初值，需用 scripts/eval-search.py 在真实照片上评测后调整
export const SCORE_LEVELS = [
  { min: 0.75, text: '很可能是同一件', cls: 'bg-emerald-500 text-white' },
  { min: 0.5, text: '相似', cls: 'bg-primary-600 text-white' },
  { min: -Infinity, text: '有点像', cls: 'bg-black/50 text-white' },
]

export function scoreLabel(score) {
  return SCORE_LEVELS.find((level) => score >= level.min)
}
```

- [ ] **Step 4: 相机按钮**

Create `frontend/src/components/CameraSearchButton.vue`:

```vue
<template>
  <span class="contents">
    <button
      type="button"
      :class="classes"
      :title="label || '拍照搜索'"
      :aria-label="label || '拍照搜索'"
      @click="input.click()"
    >
      <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="M6.827 6.175A2.31 2.31 0 0 1 5.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 0 0-1.134-.175 2.31 2.31 0 0 1-1.64-1.055l-.822-1.316a2.192 2.192 0 0 0-1.736-1.039 48.774 48.774 0 0 0-5.232 0 2.192 2.192 0 0 0-1.736 1.039l-.821 1.316Z" />
        <path stroke-linecap="round" stroke-linejoin="round" d="M16.5 12.75a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0ZM18.75 10.5h.008v.008h-.008V10.5Z" />
      </svg>
      <span v-if="label">{{ label }}</span>
    </button>
    <!-- 不加 capture：加了手机会直接进相机、不能选相册；不加会弹出「拍照 / 照片图库」选择 -->
    <input ref="input" type="file" accept="image/*" class="hidden" @change="onPick" />
  </span>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { searchByPhoto } from '../imageSearch.js'

const props = defineProps({
  // icon：搜索框旁的方形图标按钮；primary：主按钮；ghost：页眉里的文字按钮
  variant: { type: String, default: 'icon' },
  label: { type: String, default: '' },
})

const input = ref(null)
const route = useRoute()
const router = useRouter()

const classes = computed(() => ({
  icon: 'flex w-[42px] shrink-0 items-center justify-center self-stretch rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm transition-colors hover:bg-slate-50 hover:text-primary-600',
  primary: 'inline-flex items-center gap-1.5 rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-primary-700',
  ghost: 'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium text-primary-600 transition-colors hover:bg-primary-50',
}[props.variant]))

function onPick(e) {
  const file = e.target.files && e.target.files[0]
  // 清空，这样连续选同一张图也会触发 change
  e.target.value = ''
  if (!file) return
  searchByPhoto(file)
  if (route.name !== 'ImageSearch') router.push({ name: 'ImageSearch' })
}
</script>
```

- [ ] **Step 5: 搜索页**

Create `frontend/src/views/ImageSearch.vue`:

```vue
<template>
  <div>
    <PageHeader title="拍照搜索" back>
      <template #actions>
        <CameraSearchButton v-if="imageSearch.status !== 'idle'" variant="ghost" label="重新拍照" />
      </template>
    </PageHeader>

    <!-- 还没选照片：直接访问或刷新了页面 -->
    <div
      v-if="imageSearch.status === 'idle'"
      class="flex flex-col items-center rounded-2xl border border-dashed border-slate-200 bg-white py-16 text-center"
    >
      <p class="mb-4 text-sm text-slate-500">拍一张照片，找到库里的同一件东西</p>
      <CameraSearchButton variant="primary" label="拍照搜索" />
    </div>

    <template v-else>
      <!-- 查询照片 -->
      <div class="mb-4 flex items-center gap-3 rounded-2xl border border-slate-100 bg-white p-3 shadow-sm">
        <img :src="imageSearch.previewUrl" alt="查询照片" class="h-16 w-16 shrink-0 rounded-xl object-cover" />
        <p class="min-w-0 flex-1 text-sm">
          <span v-if="imageSearch.status === 'loading'" class="text-slate-500">正在识别…（约需几秒）</span>
          <span v-else-if="imageSearch.status === 'done'" class="text-slate-700">
            找到 {{ imageSearch.items.length }} 条相似记录
          </span>
          <span v-else class="text-red-600">搜索失败</span>
        </p>
      </div>

      <div
        v-if="imageSearch.status === 'done' && imageSearch.pending > 0"
        class="mb-4 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-700"
      >
        还有 {{ imageSearch.pending }} 张图片正在建立索引，结果可能不完整
      </div>

      <!-- 加载骨架 -->
      <div v-if="imageSearch.status === 'loading'" class="columns-2 gap-3">
        <div v-for="n in 4" :key="n" class="mb-3 h-48 animate-pulse break-inside-avoid rounded-2xl bg-slate-100" />
      </div>

      <!-- 出错 -->
      <div
        v-else-if="imageSearch.status === 'error'"
        class="rounded-2xl border border-red-100 bg-red-50 p-4 text-center text-sm text-red-600"
      >
        <p>{{ errorMessage }}</p>
        <button
          v-if="imageSearch.errorStatus !== 503"
          @click="retry"
          class="mt-3 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-red-600 shadow-sm transition-colors hover:bg-red-100"
        >
          重试
        </button>
      </div>

      <EmptyState v-else-if="imageSearch.items.length === 0" message="没有找到相似的记录" />

      <!-- 结果 -->
      <div v-else class="columns-2 gap-3">
        <LogCard
          v-for="hit in imageSearch.items"
          :key="hit.log.id"
          :log="hit.log"
          :image="hit.matched_image"
        >
          <template #badge>
            <span
              class="absolute left-1.5 top-1.5 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
              :class="scoreLabel(hit.score).cls"
            >
              {{ scoreLabel(hit.score).text }}
            </span>
          </template>
        </LogCard>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import LogCard from '../components/LogCard.vue'
import CameraSearchButton from '../components/CameraSearchButton.vue'
import { imageSearch, retry, scoreLabel } from '../imageSearch.js'

const errorMessage = computed(() =>
  imageSearch.errorStatus === 503
    ? '以图搜图未启用，请联系管理员放置模型文件'
    : imageSearch.error || '搜索失败',
)
</script>
```

- [ ] **Step 6: 路由**

`frontend/src/router.js`：import 区加 `import ImageSearch from './views/ImageSearch.vue'`，`routes` 数组末尾加：

```js
  { path: '/search/image', name: 'ImageSearch', component: ImageSearch },
```

- [ ] **Step 7: 列表页入口**

`frontend/src/views/LogList.vue` 的 `<!-- Search bar -->`：把外层

```vue
    <div class="relative mb-4">
```

改为两层——外层 flex、原来的 `relative` 容器包住放大镜图标和输入框，右侧放按钮：

```vue
    <div class="mb-4 flex gap-2">
      <div class="relative flex-1">
        <!-- 原来的放大镜 <svg> 和 <input>，原样保留 -->
      </div>
      <CameraSearchButton />
    </div>
```

`<script setup>` import 区加 `import CameraSearchButton from '../components/CameraSearchButton.vue'`。

- [ ] **Step 8: 构建确认**

Run: `cd frontend && npm run build`
Expected: 构建成功，无报错。

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api.js frontend/src/imageCompress.js frontend/src/imageSearch.js frontend/src/components/CameraSearchButton.vue frontend/src/views/ImageSearch.vue frontend/src/router.js frontend/src/views/LogList.vue
git commit -m "Add photo search page with camera entry on the log list

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 端到端验证与上线

**Files:** 无代码改动（除非验证发现问题）

- [ ] **Step 1: 本地端到端验证（用 `run` skill 驱动浏览器）**

后端带模型启动：

```bash
cd backend && DB_PATH=./devdata/piclog.db UPLOAD_DIR=./devuploads \
  MODEL_PATH=./devdata/models/dinov2-small.onnx \
  .venv/bin/python -m uvicorn main:app --reload --port 8080
```

前端 `cd frontend && npm run dev`。在浏览器（手机宽度 390px）中逐项确认：

1. 列表页搜索框右侧有相机按钮，高度与输入框一致
2. 选一张库里已有物品的图 → 跳到 `/search/image`，先出现骨架屏和「正在识别…」，然后结果中该日志排第一，封面是匹配到的那张图，左上角有档位标签
3. 点结果进详情，返回 → 结果仍在，没有重新请求（看 Network）
4. 「重新拍照」可以再选一张
5. 刷新 `/search/image` → 显示「拍照搜索」空状态
6. 选一个 `.txt` 改名为 `.jpg` 的文件 → 显示「无法识别的图片」和重试按钮
7. 不带 `MODEL_PATH` 重启后端，再搜 → 显示「以图搜图未启用，请联系管理员放置模型文件」，无重试按钮；此时新建日志上传图片仍正常

- [ ] **Step 2: 跑全部后端测试与前端构建**

Run: `cd backend && .venv/bin/pytest tests -q && cd ../frontend && npm run build`
Expected: 测试全部通过（1 skipped），构建成功。

- [ ] **Step 3: 向用户汇报并请求上线许可**

向用户说明上线步骤及影响：`git push` 会触发 pre-push hook 自动部署（测试 → 构建 → 推到 NAS → 重建容器 → 健康检查）；Docker 镜像增大约 60MB；部署后需运行一次 `./scripts/fetch-model.sh` 上传模型并重启容器，之后后台补算 91 张历史图片（预计 2–5 分钟）。**得到明确同意后再执行下面两步。**

- [ ] **Step 4: 部署代码**

Run: `git push`
Expected: 部署脚本最后输出「部署完成」。

- [ ] **Step 5: 上传模型并确认索引**

Run: `./scripts/fetch-model.sh`
Expected: 最后输出「✓ 完成」。

等几分钟后确认：

```bash
ssh -o BatchMode=yes root@192.168.8.10 'export PATH=/usr/local/bin:/usr/bin:/bin:$PATH; cd /volume2/homes/darlingz/pic && docker-compose logs --tail=20 piclog'
```

Expected: 出现「已为 N 张图片建立索引」，无报错。手机打开线上地址，拍一件已录入的东西搜一次。

- [ ] **Step 6: 交给用户做阈值评测**

告诉用户：给 10–20 件已录入的物品重新拍照，文件名改成 `<日志id>_xxx.jpg` 放进一个目录，运行

```bash
backend/.venv/bin/python scripts/eval-search.py <目录>
```

根据输出调整 `backend/image_search.py` 的 `MIN_SCORE` 和 `frontend/src/imageSearch.js` 的 `SCORE_LEVELS`（这是后续的独立小改动）。
