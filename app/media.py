"""Penyimpanan gambar.

TAHAP SEKARANG: file disimpan ke app/static/uploads/<folder>/ dan URL-nya
berupa path lokal. TAHAP PRODUCTION: ganti isi `save_image` dengan upload
ke Cloudinary dan kembalikan secure_url. Pemanggil tidak perlu berubah.
"""
import uuid
from pathlib import Path

from flask import current_app

ALLOWED_FOLDERS = {"berita", "galeri"}

# Tanda awal (magic bytes) untuk memastikan file benar-benar gambar.
MAGIC = {
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "gif": [b"GIF87a", b"GIF89a"],
    "webp": [b"RIFF"],  # diperiksa juga 'WEBP' di offset 8
}


class MediaError(ValueError):
    pass


def _valid_magic(ext, header):
    if ext == "webp":
        return header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    return any(header.startswith(sig) for sig in MAGIC[ext])


def save_image(file_storage, folder):
    if folder not in ALLOWED_FOLDERS:
        raise MediaError("Folder upload tidak dikenal.")
    if not file_storage or not file_storage.filename:
        raise MediaError("Tidak ada file yang dipilih.")

    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in current_app.config["ALLOWED_IMAGE_EXT"]:
        raise MediaError("Format gambar harus JPG, PNG, WEBP, atau GIF.")

    header = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    if not _valid_magic(ext, header):
        raise MediaError("File bukan gambar yang valid.")

    target_dir = Path(current_app.config["UPLOAD_DIR"]) / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(target_dir / name)
    return f"/static/uploads/{folder}/{name}"


def validate_image_path(value):
    """Validasi path gambar yang diketik manual.

    Diterima: path lokal di /static/ (tanpa '..') atau URL https://.
    Kosong diperbolehkan (berarti tanpa gambar).
    """
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("https://") or value.startswith("http://"):
        return value
    if value.startswith("/static/") and ".." not in value and "\\" not in value:
        return value
    raise MediaError("Path gambar harus diawali /static/ atau https://")


def list_uploads():
    """Daftar path gambar yang sudah ada di folder upload (untuk pilihan di form)."""
    base = Path(current_app.config["UPLOAD_DIR"])
    if not base.exists():
        return []
    files = []
    for path in base.rglob("*"):
        if path.is_file() and path.suffix.lower().lstrip(".") in current_app.config["ALLOWED_IMAGE_EXT"]:
            files.append("/static/uploads/" + path.relative_to(base).as_posix())
    return sorted(files)
