import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def spa(tmp_path, monkeypatch, anon_client):
    """带前端静态目录的应用；静态目录旁边放一个「机密」文件。"""
    import main
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>spa</html>")
    (static / "favicon.ico").write_bytes(b"icon")
    (tmp_path / "secret.db").write_text("password hashes")
    monkeypatch.setattr(main, "STATIC_DIR", str(static))
    return TestClient(main.create_app())


def test_static_file_and_fallback(spa):
    assert spa.get("/favicon.ico").content == b"icon"
    assert spa.get("/logs/12").text == "<html>spa</html>"


@pytest.mark.parametrize("path", ["/..%2Fsecret.db", "/%2E%2E%2Fsecret.db", "/assets%2F..%2F..%2Fsecret.db"])
def test_cannot_escape_static_dir(spa, path):
    resp = spa.get(path)
    assert "password hashes" not in resp.text
