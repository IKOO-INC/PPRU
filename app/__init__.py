import secrets
import sys
from datetime import date
from pathlib import Path

from flask import Flask, render_template, request

from .auth import csrf_token, init_admin
from .config import Config
from .defaults import DEFAULT_SETTINGS
from .seed import DUMMY_BERITA, DUMMY_GALERI
from .storage.json_store import write_json
from .storage.repositories import (
    AdminRepository,
    BeritaRepository,
    GalleryRepository,
    SettingsRepository,
)
from .utils import format_tanggal, paragraphs, tanggal_harian


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        print(
            "[PPRU] SECRET_KEY belum diset. Sesi login akan hilang setiap server restart. "
            "Set SECRET_KEY di environment untuk production.",
            file=sys.stderr,
        )

    data_dir = Path(app.config["DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)

    # Repository disimpan di satu tempat. Ganti isinya saat pindah ke MongoDB.
    settings_repo = SettingsRepository(data_dir / "settings.json", DEFAULT_SETTINGS)
    settings_repo.ensure_file()

    for name, seed in (("berita.json", DUMMY_BERITA), ("galeri.json", DUMMY_GALERI)):
        if not (data_dir / name).exists():
            write_json(data_dir / name, seed)
    admin_repo = AdminRepository(data_dir / "admin.json")
    app.extensions["ppru"] = {
        "berita": BeritaRepository(data_dir / "berita.json"),
        "galeri": GalleryRepository(data_dir / "galeri.json"),
        "settings": settings_repo,
        "admin": admin_repo,
    }
    init_admin(app, admin_repo)

    from .admin import bp as admin_bp
    from .public import bp as public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    app.jinja_env.filters["tanggal"] = format_tanggal
    app.jinja_env.filters["tanggal_harian"] = tanggal_harian
    app.jinja_env.filters["paragraf"] = paragraphs

    @app.context_processor
    def inject_globals():
        from flask import session

        settings = app.extensions["ppru"]["settings"].all()
        return {
            "site": settings["identitas"],
            "csrf_token": csrf_token,
            "is_admin": bool(session.get("admin")),
            "current_path": request.path,
            "year": date.today().year,
        }

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp

    @app.errorhandler(400)
    def bad_request(err):
        return render_template("error.html", code=400, message=err.description), 400

    @app.errorhandler(404)
    def not_found(err):
        return render_template("error.html", code=404, message="Halaman tidak ditemukan."), 404

    @app.errorhandler(413)
    def too_large(err):
        return render_template(
            "error.html", code=413, message="Ukuran file terlalu besar (maksimal 5 MB)."
        ), 413

    return app
