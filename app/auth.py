import hmac
import secrets
import sys
import time

from flask import abort, current_app, request, session
from werkzeug.security import generate_password_hash

# Percobaan login gagal per IP: {ip: [timestamp, ...]} (in-memory, cukup untuk satu proses).
_failed_logins = {}


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def verify_csrf():
    sent = request.form.get("csrf_token", "")
    expected = session.get("_csrf", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, description="Token keamanan tidak valid. Muat ulang halaman dan coba lagi.")


def _client_ip():
    return request.remote_addr or "unknown"


def login_locked():
    window = current_app.config["LOGIN_WINDOW_SECONDS"]
    now = time.time()
    attempts = [t for t in _failed_logins.get(_client_ip(), []) if now - t < window]
    _failed_logins[_client_ip()] = attempts
    return len(attempts) >= current_app.config["LOGIN_MAX_ATTEMPTS"]


def record_failed_login():
    _failed_logins.setdefault(_client_ip(), []).append(time.time())


def clear_failed_logins():
    _failed_logins.pop(_client_ip(), None)


def init_admin(app, repo):
    """Buat akun admin pertama kali. Password diambil dari ADMIN_PASSWORD;
    jika kosong, dibuat acak dan ditampilkan sekali di konsol."""
    if repo.get() is not None:
        return
    password = app.config.get("ADMIN_PASSWORD")
    generated = False
    if not password:
        password = secrets.token_urlsafe(12)
        generated = True
    repo.save(app.config["ADMIN_USERNAME"], generate_password_hash(password))
    if generated:
        print(
            "\n[PPRU] Akun admin dibuat. Username: "
            f"{app.config['ADMIN_USERNAME']} | Password sementara: {password}\n"
            "[PPRU] Segera ganti lewat menu Akun di dashboard admin.\n",
            file=sys.stderr,
        )
