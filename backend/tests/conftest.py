import os
import sys
import sqlite3
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# 必须在 import database / main 之前设置：两者在模块级读取这些环境变量
_TMP = tempfile.mkdtemp(prefix="piclog-test-")
os.environ["DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["UPLOAD_DIR"] = os.path.join(_TMP, "uploads")
# 指向不存在的目录，让 main.py 跳过 SPA catch-all 挂载，否则 404 会被兜底路由吞掉
os.environ["STATIC_DIR"] = os.path.join(_TMP, "no-static")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
from main import app  # noqa: E402


def _reset_db():
    for suffix in ("", "-wal", "-shm"):
        path = database.DB_PATH + suffix
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture()
def client():
    _reset_db()
    # TestClient 进入上下文时会触发 startup，startup 里会调 init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db_conn():
    conn = sqlite3.connect(database.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    yield conn
    conn.close()
