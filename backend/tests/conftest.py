import os
import shutil
import sys
import sqlite3
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# 必须在 import database / main 之前设置：两者在模块级读取这些环境变量
_TMP = tempfile.mkdtemp(prefix="piclog-test-")
os.environ["DB_PATH"] = os.path.join(_TMP, "data", "piclog.db")
os.environ["UPLOAD_DIR"] = os.path.join(_TMP, "uploads")
os.environ["INITIAL_USER_PASSWORD"] = "test-password-1"
os.environ.pop("ADMIN_PASSWORD", None)
os.environ.pop("ADMIN_PATH", None)
# 指向不存在的目录，让 main.py 跳过 SPA catch-all 挂载，否则 404 会被兜底路由吞掉
os.environ["STATIC_DIR"] = os.path.join(_TMP, "no-static")
# 默认没有模型：需要向量的测试用 fake_embedder 注入假模型
os.environ["MODEL_PATH"] = os.path.join(_TMP, "no-model.onnx")
# 测试里不启动后台索引线程，改为直接调用 indexer.process_pending()，避免依赖线程时序
os.environ["INDEXER_THREAD"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import storage  # noqa: E402
from main import app  # noqa: E402


def _reset_storage():
    for d in (storage.DATA_DIR, storage.UPLOAD_ROOT):
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def client():
    _reset_storage()
    # TestClient 进入上下文时会触发 startup，startup 里会跑 bootstrap
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db_conn():
    conn = sqlite3.connect(storage.user_db_path(1))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    yield conn
    conn.close()


@pytest.fixture()
def fake_embedder():
    """注入按图片平均颜色生成向量的假模型：颜色相同 = 相似度 1，红与蓝 ≈ 0。"""
    import embedding
    from tests.helpers import mean_color_vector

    embedding.set_embedder(mean_color_vector)
    yield
    embedding.set_embedder(None)


def pytest_configure(config):
    config.addinivalue_line("markers", "model: 需要真实模型文件的测试（默认跳过）")
