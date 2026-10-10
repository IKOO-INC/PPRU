import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    # Data JSON (berita, galeri, pengaturan situs, akun admin)
    DATA_DIR = Path(os.environ.get("PPRU_DATA_DIR", BASE_DIR / "data"))
    # Penyimpanan upload sementara (lokal). Nanti diganti Cloudinary.
    UPLOAD_DIR = BASE_DIR / "app" / "static" / "uploads"
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB per request
    ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif"}

    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")  # dipakai saat akun dibuat pertama kali

    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_WINDOW_SECONDS = 15 * 60

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE") == "1"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 jam
