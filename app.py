"""Flask application for the PPRU public portal and JSON preferences admin."""
import hmac
import os
import secrets
from pathlib import Path, PurePosixPath

from flask import Flask, abort, redirect, render_template, request, session, url_for

from content_store import JsonContentStore


BASE_DIR = Path(__file__).resolve().parent
ADMIN_COMPONENTS = (
    ("brand", "Identitas & Logo"),
    ("navigation", "Navigasi"),
    ("hero", "Hero Beranda"),
    ("stats", "Statistik"),
    ("programs", "Program Akademik"),
    ("profile", "Profil & Sejarah"),
    ("news", "Berita"),
    ("works", "Karya Santri"),
    ("gallery", "Galeri"),
    ("events", "Agenda"),
    ("faq", "FAQ"),
    ("contact", "Kontak"),
    ("admission", "PSB"),
    ("hafalan", "Hafalan"),
)
ADMIN_COMPONENT_IDS = {component_id for component_id, _ in ADMIN_COMPONENTS}


def _form_value(form, key, current=""):
    """Return a trimmed form value, preserving the current value if omitted."""
    if key not in form:
        return current
    return form.get(key, "").strip()


def _safe_asset_path(value, current):
    """Only accept local static paths; prevent traversal and arbitrary schemes."""
    candidate = value.strip()
    if not candidate:
        return current
    if not candidate.startswith("/static/") or "\\" in candidate:
        return current
    if ".." in PurePosixPath(candidate).parts:
        return current
    return candidate


def _apply_admin_form(content, form, component):
    """Update one preference panel while leaving the rest of the JSON intact."""
    site = content.setdefault("site", {})

    if component == "brand":
        site["name"] = _form_value(form, "site_name", site.get("name", ""))
        site["short_name"] = _form_value(form, "short_name", site.get("short_name", ""))
        site["description"] = _form_value(form, "site_description", site.get("description", ""))
        site["footer_note"] = _form_value(form, "footer_note", site.get("footer_note", ""))
        for key in ("login_label", "login_url", "admission_label", "admission_url"):
            if key in site:
                site[key] = _form_value(form, key, site.get(key, ""))
        site["logo_path"] = _safe_asset_path(
            _form_value(form, "logo_path", site.get("logo_path", "")),
            site.get("logo_path", "/static/images/mark.svg"),
        )
        site["placeholder_image"] = _safe_asset_path(
            _form_value(form, "fallback_image_path", site.get("placeholder_image", "")),
            site.get("placeholder_image", "/static/images/pondok-campus.jpg"),
        )

    elif component == "navigation":
        for index, item in enumerate(site.get("navigation", [])):
            item["label"] = _form_value(form, f"nav_label_{index}", item.get("label", ""))
            item["url"] = _form_value(form, f"nav_url_{index}", item.get("url", ""))

    elif component == "hero":
        hero = content.setdefault("hero", {})
        for key in ("title", "description", "eyebrow", "primary_label", "primary_url", "secondary_label", "secondary_url", "image_note"):
            hero[key] = _form_value(form, key, hero.get(key, ""))
        hero["image"] = _safe_asset_path(_form_value(form, "hero_image", hero.get("image", "")), hero.get("image", ""))
        hero["image_alt"] = _form_value(form, "hero_image_alt", hero.get("image_alt", ""))

    elif component == "stats":
        for index, item in enumerate(content.get("stats", [])):
            item["value"] = _form_value(form, f"stat_value_{index}", item.get("value", ""))
            item["label"] = _form_value(form, f"stat_label_{index}", item.get("label", ""))

    elif component == "programs":
        intro = content.setdefault("program_intro", {})
        for key in ("eyebrow", "title", "description"):
            intro[key] = _form_value(form, f"program_intro_{key}", intro.get(key, ""))
        for index, item in enumerate(content.get("programs", [])):
            for key in ("title", "category", "description"):
                item[key] = _form_value(form, f"program_{key}_{index}", item.get(key, ""))

    elif component == "profile":
        profile = content.setdefault("profile", {})
        history = content.setdefault("history", {})
        for key in ("title", "subtitle", "history_title", "vision_title", "vision"):
            profile[key] = _form_value(form, f"profile_{key}", profile.get(key, ""))
        for index, paragraph in enumerate(profile.get("history_paragraphs", [])):
            profile["history_paragraphs"][index] = _form_value(
                form, f"history_paragraph_{index}", paragraph
            )
        profile["image"] = _safe_asset_path(
            _form_value(form, "profile_image", profile.get("image", "")),
            profile.get("image", ""),
        )
        history["title"] = _form_value(form, "history_block_title", history.get("title", ""))
        history["intro"] = _form_value(form, "history_intro", history.get("intro", ""))
        history["body"] = _form_value(form, "history_body", history.get("body", ""))
        history["quote"] = _form_value(form, "history_quote", history.get("quote", ""))
        history["image"] = _safe_asset_path(
            _form_value(form, "history_image", history.get("image", "")),
            history.get("image", ""),
        )
        for index, mission in enumerate(profile.get("mission", [])):
            profile["mission"][index] = _form_value(form, f"mission_{index}", mission)

    elif component == "news":
        for index, item in enumerate(content.get("news", [])):
            for key in ("title", "category", "excerpt", "date", "image_alt"):
                item[key] = _form_value(form, f"news_{key}_{index}", item.get(key, ""))
            item["image"] = _safe_asset_path(
                _form_value(form, f"news_image_{index}", item.get("image", "")),
                item.get("image", ""),
            )

    elif component == "works":
        for index, item in enumerate(content.get("works", [])):
            for key in ("title", "subtitle", "excerpt", "label"):
                item[key] = _form_value(form, f"work_{key}_{index}", item.get(key, ""))
            item["image"] = _safe_asset_path(
                _form_value(form, f"work_image_{index}", item.get("image", "")),
                item.get("image", ""),
            )

    elif component == "gallery":
        for index, item in enumerate(content.get("gallery", [])):
            for key in ("title", "caption", "category", "shape"):
                item[key] = _form_value(form, f"gallery_{key}_{index}", item.get(key, ""))
            item["image"] = _safe_asset_path(
                _form_value(form, f"gallery_image_{index}", item.get("image", "")),
                item.get("image", ""),
            )

    elif component == "events":
        for index, item in enumerate(content.get("events", [])):
            for key in ("day", "month", "title", "category", "description"):
                item[key] = _form_value(form, f"event_{key}_{index}", item.get(key, ""))

    elif component == "faq":
        for index, item in enumerate(content.get("faq", [])):
            item["question"] = _form_value(form, f"faq_question_{index}", item.get("question", ""))
            item["answer"] = _form_value(form, f"faq_answer_{index}", item.get("answer", ""))

    elif component == "contact":
        contact = content.setdefault("contact", {})
        for key in ("title", "subtitle", "address", "phone", "email"):
            contact[key] = _form_value(form, f"contact_{key}", contact.get(key, ""))
        contact["map_image"] = _safe_asset_path(
            _form_value(form, "contact_map_image", contact.get("map_image", "")),
            contact.get("map_image", site.get("placeholder_image", "")),
        )

    elif component == "admission":
        admission = content.setdefault("admission", {})
        for key in ("title", "description", "eyebrow"):
            admission[key] = _form_value(form, f"admission_{key}", admission.get(key, ""))
        admission["image"] = _safe_asset_path(
            _form_value(form, "admission_image", admission.get("image", "")),
            admission.get("image", ""),
        )
        for index, item in enumerate(admission.get("programs", [])):
            item["name"] = _form_value(form, f"admission_program_name_{index}", item.get("name", ""))
            item["detail"] = _form_value(form, f"admission_program_detail_{index}", item.get("detail", ""))
        for index, item in enumerate(admission.get("steps", [])):
            for key in ("number", "title", "description"):
                item[key] = _form_value(form, f"admission_step_{key}_{index}", item.get(key, ""))
        for index, item in enumerate(admission.get("requirements", [])):
            for key in ("title", "description"):
                item[key] = _form_value(form, f"admission_requirement_{key}_{index}", item.get(key, ""))

    elif component == "hafalan":
        hafalan = content.setdefault("hafalan", {})
        for key in ("title", "eyebrow", "description", "frequent_title", "frequent_description"):
            hafalan[key] = _form_value(form, f"hafalan_{key}", hafalan.get(key, ""))
        for index, item in enumerate(hafalan.get("frequent_items", [])):
            for key in ("surah", "note", "count"):
                item[key] = _form_value(form, f"hafalan_item_{key}_{index}", item.get(key, ""))


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "local-development-key-change-before-production"),
        CONTENT_FILE=BASE_DIR / "preferensi.json",
        SEED_CONTENT_FILE=BASE_DIR / "data" / "site.json",
        # Change this through the ADMIN_PASSWORD environment variable before deployment.
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", "admin123"),
    )
    if test_config:
        app.config.update(test_config)

    store = JsonContentStore(app.config["CONTENT_FILE"])
    seed_store = JsonContentStore(app.config["SEED_CONTENT_FILE"])

    def load_content():
        try:
            return store.load()
        except FileNotFoundError:
            return seed_store.load()

    def page_context(active_page, **extra):
        content = load_content()
        return {
            "site": content.get("site", {}),
            "data": content,
            "active_page": active_page,
            **extra,
        }

    def csrf_value():
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    def validate_csrf():
        expected = session.get("_csrf_token", "")
        received = request.form.get("csrf_token", "")
        if not expected or not received or not hmac.compare_digest(expected, received):
            abort(400, description="Sesi formulir tidak valid. Silakan muat ulang halaman.")

    app.jinja_env.globals["csrf_token"] = csrf_value

    @app.get("/")
    def home():
        return render_template("index.html", **page_context("home"))

    @app.get("/profil")
    def profile():
        return render_template("profile.html", **page_context("profile"))

    @app.get("/akademik")
    @app.get("/program")
    def programs():
        return render_template("programs.html", **page_context("programs"))

    @app.get("/berita")
    def news():
        return render_template("news.html", **page_context("news"))

    @app.get("/berita/<slug>")
    def news_detail(slug):
        content = load_content()
        post = next(
            (item for item in content.get("news", []) if item.get("slug") == slug),
            None,
        )
        if post is None:
            abort(404)
        return render_template(
            "news_detail.html",
            site=content.get("site", {}),
            data=content,
            active_page="news",
            post=post,
        )

    @app.get("/galeri")
    def gallery():
        return render_template("gallery.html", **page_context("gallery"))

    @app.get("/hafalan")
    def hafalan():
        return render_template("hafalan.html", **page_context("hafalan"))

    @app.get("/kontak")
    def contact():
        return render_template("contact.html", **page_context("contact"))

    @app.get("/psb")
    def admission():
        return render_template("admission.html", **page_context("admission"))

    @app.get("/masuk")
    def login():
        return render_template("login.html", **page_context(None))

    @app.get("/admin")
    def admin():
        content = load_content()
        if not session.get("admin_authenticated"):
            return render_template(
                "admin_login.html",
                site=content.get("site", {}),
                data=content,
                active_page=None,
                error=None,
            )
        component = request.args.get("tab", "brand")
        if component not in ADMIN_COMPONENT_IDS:
            component = "brand"
        return render_template(
            "admin.html",
            site=content.get("site", {}),
            data=content,
            active_page=None,
            components=ADMIN_COMPONENTS,
            active_component=component,
            saved=request.args.get("saved") == "1",
        )

    @app.post("/admin/login")
    def admin_login():
        content = load_content()
        validate_csrf()
        entered_password = request.form.get("password", "")
        admin_password = str(app.config["ADMIN_PASSWORD"])
        if not hmac.compare_digest(entered_password, admin_password):
            return render_template(
                "admin_login.html",
                site=content.get("site", {}),
                data=content,
                active_page=None,
                error="Kata sandi admin tidak sesuai.",
            ), 401
        session.clear()
        session["admin_authenticated"] = True
        csrf_value()
        return redirect(url_for("admin"))

    @app.post("/admin/save")
    def admin_save():
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin"))
        validate_csrf()
        component = request.form.get("component", "")
        if component not in ADMIN_COMPONENT_IDS:
            abort(400, description="Komponen admin tidak dikenal.")
        content = load_content()
        _apply_admin_form(content, request.form, component)
        store.save(content)
        return redirect(url_for("admin", tab=component, saved="1"))

    @app.post("/admin/logout")
    def admin_logout():
        validate_csrf()
        session.clear()
        return redirect(url_for("admin"))

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html", **page_context(None)), 404

    return app


app = create_app()

if __name__ == "__main__":
    # 0.0.0.0 makes the development server accessible in the preview environment.
    app.run(host="0.0.0.0", port=5000, debug=True)
