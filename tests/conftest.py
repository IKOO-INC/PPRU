import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402

PASSWORD = "rahasia-123"
CSRF = "token-uji-123"
# PNG minimal yang valid (magic bytes + data dummy). Cukup untuk validasi tipe.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture(autouse=True)
def _reset_login_limiter():
    from app import auth
    auth._failed_logins.clear()
    yield
    auth._failed_logins.clear()


@pytest.fixture()
def app(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in ("berita.json", "galeri.json", "settings.json"):
        shutil.copy(ROOT / "data" / name, data_dir / name)
    upload_dir = tmp_path / "uploads"
    (upload_dir / "berita").mkdir(parents=True)
    (upload_dir / "galeri").mkdir(parents=True)
    application = create_app({
        "TESTING": True,
        "DATA_DIR": data_dir,
        "UPLOAD_DIR": upload_dir,
        "ADMIN_PASSWORD": PASSWORD,
        "SECRET_KEY": "kunci-uji",
    })
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, password=PASSWORD):
    resp = client.post("/admin/login", data={"username": "admin", "password": password,
                                              "csrf_token": "x"}, follow_redirects=False)
    return resp


def admin_client(app):
    """Client yang sudah login dan punya token CSRF yang diketahui."""
    c = app.test_client()
    c.get("/admin/login")
    with c.session_transaction() as s:
        s["_csrf"] = CSRF
    resp = c.post("/admin/login", data={"username": "admin", "password": PASSWORD, "csrf_token": CSRF})
    assert resp.status_code == 302, resp.data
    with c.session_transaction() as s:
        s["_csrf"] = CSRF
    return c
