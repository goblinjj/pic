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


REAL_MODEL = os.path.expanduser(os.environ.get("PICLOG_TEST_MODEL", ""))


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
