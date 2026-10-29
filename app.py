"""Flask application for the PPRU public portal and JSON preferences admin."""
import hmac
import os
import secrets
import threading
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from markupsafe import Markup

from cloudinary_service import CloudinaryConfigurationError, InvalidImageUpload, upload_image
from content_store import JsonPortalStore
from nadzom_service import build_book_catalog, load_book
from news_service import (
    format_indonesian_date,
    legacy_article_html,
    now_jakarta,
    parse_local_datetime,
    public_content,
    published_at_value,
    rich_text_plain_text,
    sanitize_rich_text,
    slugify,
    to_local_input,
)


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
    ("hafalan", "Sambung Nadzom"),
)
ADMIN_COMPONENT_IDS = {component_id for component_id, _ in ADMIN_COMPONENTS}


def _form_value(form, key, current=""):
    """Return a trimmed form value, preserving the current value if omitted."""
    if key not in form:
        return current
    return form.get(key, "").strip()


def _redacted_error_detail(error, sensitive_values=()):
    """Return a short diagnostic message without logging Cloudinary credentials."""
    detail = f"{type(error).__name__}: {error}"
    for secret in sorted({str(value) for value in sensitive_values if value}, key=len, reverse=True):
        detail = detail.replace(secret, "[redacted]")
    return detail[:500]


def _migrate_legacy_hafalan_preferences(content):
    """Replace the previous Quran/juz challenge defaults and remove verse-summary fields."""
    hafalan = content.get("hafalan")
    if not isinstance(hafalan, dict):
        return False
    replacements = {
        "title": ("Sambung Ayat Challenge", "Sambung Nadzom Challenge"),
        "eyebrow": ("Uji hafalanmu di sini", "Uji hafalan nadzommu"),
        "description": (
            "Pilih rentang juz dan jumlah soal untuk memulai latihan hafalan.",
            "Pilih kitab nahwu, rentang bab, dan jumlah soal untuk menguji hafalan nadzom.",
        ),
    }
    changed = False
    for key, (old_value, new_value) in replacements.items():
        if hafalan.get(key) == old_value:
            hafalan[key] = new_value
            changed = True
    for key in ("frequent_title", "frequent_description", "frequent_items"):
        if key in hafalan:
            hafalan.pop(key)
            changed = True
    return changed


def _safe_image_url(value, current):
    """Accept Cloudinary HTTPS URLs and unchanged legacy local assets only."""
    candidate = str(value or "").strip()
    current = str(current or "")
    if not candidate:
        return current
    if candidate.startswith("/static/"):
        if candidate != current or "\\" in candidate or ".." in PurePosixPath(candidate).parts:
            return current
        return candidate
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        return current
    path_parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.hostname != "res.cloudinary.com"
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or len(path_parts) < 4
        or path_parts[1:3] != ["image", "upload"]
    ):
        return current

    required_transformations = ("w_1600", "h_1600", "q_auto", "f_auto")
    if not all(item in parsed.path for item in required_transformations):
        prefix, marker, suffix = parsed.path.partition("/image/upload/")
        if marker:
            segments = suffix.split("/")
            version_index = next(
                (index for index, segment in enumerate(segments) if segment.startswith("v") and segment[1:].isdigit()),
                0,
            )
            segments.insert(version_index, "c_limit,h_1600,q_auto:good,w_1600,f_auto")
            parsed = parsed._replace(path=f"{prefix}{marker}{'/'.join(segments)}")
            candidate = urlunsplit(parsed)
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
        site["logo_path"] = _safe_image_url(
            _form_value(form, "logo_path", site.get("logo_path", "")),
            site.get("logo_path", "/static/images/mark.svg"),
        )
        site["placeholder_image"] = _safe_image_url(
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
        hero["image"] = _safe_image_url(_form_value(form, "hero_image", hero.get("image", "")), hero.get("image", ""))
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
        profile["image"] = _safe_image_url(
            _form_value(form, "profile_image", profile.get("image", "")),
            profile.get("image", ""),
        )
        history["title"] = _form_value(form, "history_block_title", history.get("title", ""))
        history["intro"] = _form_value(form, "history_intro", history.get("intro", ""))
        history["body"] = _form_value(form, "history_body", history.get("body", ""))
        history["quote"] = _form_value(form, "history_quote", history.get("quote", ""))
        history["image"] = _safe_image_url(
            _form_value(form, "history_image", history.get("image", "")),
            history.get("image", ""),
        )
        for index, mission in enumerate(profile.get("mission", [])):
            profile["mission"][index] = _form_value(form, f"mission_{index}", mission)

    elif component == "news":
        for index, item in enumerate(content.get("news", [])):
            for key in ("title", "category", "excerpt", "date", "image_alt"):
                item[key] = _form_value(form, f"news_{key}_{index}", item.get(key, ""))
            item["image"] = _safe_image_url(
                _form_value(form, f"news_image_{index}", item.get("image", "")),
                item.get("image", ""),
            )

    elif component == "works":
        for index, item in enumerate(content.get("works", [])):
            for key in ("title", "subtitle", "excerpt", "label"):
                item[key] = _form_value(form, f"work_{key}_{index}", item.get(key, ""))
            item["image"] = _safe_image_url(
                _form_value(form, f"work_image_{index}", item.get("image", "")),
                item.get("image", ""),
            )

    elif component == "gallery":
        for index, item in enumerate(content.get("gallery", [])):
            for key in ("title", "caption", "category", "shape"):
                item[key] = _form_value(form, f"gallery_{key}_{index}", item.get(key, ""))
            item["image"] = _safe_image_url(
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
        contact["map_image"] = _safe_image_url(
            _form_value(form, "contact_map_image", contact.get("map_image", "")),
            contact.get("map_image", site.get("placeholder_image", "")),
        )

    elif component == "admission":
        admission = content.setdefault("admission", {})
        for key in ("title", "description", "eyebrow"):
            admission[key] = _form_value(form, f"admission_{key}", admission.get(key, ""))
        admission["image"] = _safe_image_url(
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
        _migrate_legacy_hafalan_preferences(content)
        for key in ("title", "eyebrow", "description"):
            hafalan[key] = _form_value(form, f"hafalan_{key}", hafalan.get(key, ""))


def _unique_news_slug(items, requested_slug, current_slug=None):
    base_slug = slugify(requested_slug)
    existing = {item.get("slug") for item in items if item.get("slug") != current_slug}
    candidate = base_slug
    suffix = 2
    while candidate in existing:
        candidate = f"{base_slug}-{suffix}"
        suffix += 1
    return candidate


def _view_count(item):
    try:
        return max(0, int(item.get("views", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _ensure_gallery_ids(content):
    """Assign persistent identifiers to legacy gallery entries that lack one."""
    changed = False
    used_ids = set()
    for item in content.setdefault("gallery", []):
        item_id = str(item.get("id", "")).strip()
        if not item_id or item_id in used_ids:
            item_id = secrets.token_urlsafe(12)
            item["id"] = item_id
            changed = True
        used_ids.add(item_id)
    return changed



def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "local-development-key-change-before-production"),
        CONTENT_FILE=BASE_DIR / "preferensi.json",
        NEWS_FILE=None,
        GALLERY_FILE=None,
        SEED_CONTENT_FILE=BASE_DIR / "data" / "site.json",
        NEWS_SEED_FILE=BASE_DIR / "data" / "berita.json",
        GALLERY_SEED_FILE=BASE_DIR / "data" / "gallery.json",
        CLOUDINARY_CLOUD_NAME=os.environ.get("CLOUDINARY_CLOUD_NAME", "mcdrphte"),
        CLOUDINARY_API_KEY=os.environ.get("CLOUDINARY_API_KEY", "184529251999341"),
        CLOUDINARY_API_SECRET=os.environ.get("CLOUDINARY_API_SECRET", "zK9jMKb47AIVub-kX5TsRqQAwCA"),
        # Allow multipart framing overhead while cloudinary_service enforces the 10 MiB file limit.
        MAX_CONTENT_LENGTH=11 * 1024 * 1024,
        # Change this through the ADMIN_PASSWORD environment variable before deployment.
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", "admin123"),
    )
    if test_config:
        app.config.update(test_config)

    preferences_file = Path(app.config["CONTENT_FILE"])
    news_file = app.config["NEWS_FILE"] or preferences_file.with_name("berita.json")
    gallery_file = app.config["GALLERY_FILE"] or preferences_file.with_name("gallery.json")
    store = JsonPortalStore(
        preferences_file=preferences_file,
        news_file=news_file,
        gallery_file=gallery_file,
        seed_preferences_file=app.config["SEED_CONTENT_FILE"],
        seed_news_file=app.config["NEWS_SEED_FILE"],
        seed_gallery_file=app.config["GALLERY_SEED_FILE"],
    )
    content_lock = threading.RLock()

    def load_content():
        content = store.load()
        if _migrate_legacy_hafalan_preferences(content):
            store.save(content)
        return content

    def page_context(active_page, **extra):
        content = public_content(load_content())
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

    def render_admin_news_form(post, is_edit, error=None, status_code=200):
        content = load_content()
        body_html = post.get("body_html") or legacy_article_html(post)
        return render_template(
            "admin_news_form.html",
            site=content.get("site", {}),
            data=content,
            active_page=None,
            post=post,
            editor_html=Markup(sanitize_rich_text(body_html)),
            published_at_input=to_local_input(post.get("published_at")),
            is_edit=is_edit,
            error=error,
        ), status_code

    def render_admin_gallery_form(item, is_edit, error=None, status_code=200):
        content = load_content()
        return render_template(
            "admin_gallery_form.html",
            site=content.get("site", {}),
            data=content,
            active_page=None,
            item=item,
            is_edit=is_edit,
            error=error,
        ), status_code

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
        with content_lock:
            content = load_content()
            post = next(
                (
                    item for item in content.get("news", [])
                    if item.get("slug") == slug and item.get("status", "published") == "published"
                ),
                None,
            )
            if post is None:
                abort(404)
            try:
                post["views"] = max(0, int(post.get("views", 0) or 0)) + 1
            except (TypeError, ValueError):
                post["views"] = 1
            store.save(content)
            content = public_content(content)

        post = next((item for item in content["news"] if item.get("slug") == slug), None)
        if post is None:
            abort(404)
        body_html = post.get("body_html") or legacy_article_html(post)
        post["rendered_body"] = Markup(sanitize_rich_text(body_html))
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
        return render_template(
            "hafalan.html",
            **page_context("hafalan"),
            book_catalog=build_book_catalog(),
        )

    @app.get("/hafalan/data/<book_id>")
    def hafalan_book_data(book_id):
        records = load_book(book_id)
        if records is None:
            abort(404)
        response = jsonify(records)
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response

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
        with content_lock:
            content = load_content()
            if _ensure_gallery_ids(content):
                store.save(content)
        component = request.args.get("tab", "brand")
        if component not in ADMIN_COMPONENT_IDS:
            component = "brand"
        news_items = sorted(content.get("news", []), key=published_at_value, reverse=True)
        return render_template(
            "admin.html",
            site=content.get("site", {}),
            data=content,
            active_page=None,
            components=ADMIN_COMPONENTS,
            active_component=component,
            saved=request.args.get("saved") == "1",
            news_items=news_items,
            gallery_items=content.get("gallery", []),
        )

    @app.get("/admin/berita/baru")
    def admin_news_new():
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin"))
        content = load_content()
        post = {
            "slug": "",
            "title": "",
            "category": "Kegiatan",
            "excerpt": "",
            "image": "",
            "image_alt": "",
            "status": "published",
            "views": 0,
            "body_html": "",
        }
        return render_admin_news_form(post, is_edit=False)

    @app.get("/admin/berita/<slug>/edit")
    def admin_news_edit(slug):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin"))
        content = load_content()
        post = next((item for item in content.get("news", []) if item.get("slug") == slug), None)
        if post is None:
            abort(404)
        return render_admin_news_form(post, is_edit=True)

    @app.post("/admin/berita/simpan")
    def admin_news_save():
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin"))
        validate_csrf()
        with content_lock:
            content = load_content()
            items = content.setdefault("news", [])
            original_slug = request.form.get("original_slug", "").strip()
            existing_index = next(
                (index for index, item in enumerate(items) if item.get("slug") == original_slug),
                None,
            ) if original_slug else None
            if original_slug and existing_index is None:
                abort(404)
            existing = items[existing_index] if existing_index is not None else {}
            title = request.form.get("title", "").strip()
            submitted_image = request.form.get("image", "").strip()
            existing_image = existing.get("image", "")
            image_url = _safe_image_url(submitted_image, existing_image)
            form_error = None
            if not title:
                form_error = "Judul berita wajib diisi."
            elif not image_url:
                form_error = "Upload foto cover ke Cloudinary atau masukkan URL Cloudinary."
            elif submitted_image and image_url == existing_image and submitted_image != existing_image:
                form_error = "URL foto harus menggunakan HTTPS Cloudinary atau gunakan tombol Upload."
            if form_error:
                post = {
                    **existing,
                    "slug": request.form.get("slug", "").strip(),
                    "title": title,
                    "category": request.form.get("category", "Kegiatan").strip() or "Kegiatan",
                    "excerpt": request.form.get("excerpt", "").strip(),
                    "image": submitted_image or existing_image,
                    "image_alt": request.form.get("image_alt", "").strip() or title,
                    "status": request.form.get("status", "published").strip(),
                    "published_at": request.form.get("published_at", ""),
                    "body_html": request.form.get("body_html", ""),
                }
                return render_admin_news_form(
                    post,
                    is_edit=existing_index is not None,
                    error=form_error,
                    status_code=400,
                )

            requested_slug = request.form.get("slug", "").strip() or title
            slug = _unique_news_slug(items, requested_slug, current_slug=original_slug or None)
            body_html = sanitize_rich_text(request.form.get("body_html", ""))
            body_text = rich_text_plain_text(body_html)
            excerpt = request.form.get("excerpt", "").strip() or body_text[:220]
            if len(body_text) > 220 and not request.form.get("excerpt", "").strip():
                excerpt = excerpt.rstrip() + "…"
            status = request.form.get("status", "published").strip()
            if status not in {"published", "draft"}:
                status = "published"
            published_at = parse_local_datetime(request.form.get("published_at", ""))
            post = {
                **existing,
                "slug": slug,
                "title": title,
                "category": request.form.get("category", "Kegiatan").strip() or "Kegiatan",
                "excerpt": excerpt,
                "date": format_indonesian_date(published_at),
                "published_at": published_at.isoformat(timespec="minutes"),
                "status": status,
                "views": _view_count(existing),
                "image": image_url,
                "image_alt": request.form.get("image_alt", "").strip() or title,
                "body_html": body_html,
                "updated_at": now_jakarta().isoformat(timespec="minutes"),
            }
            if not existing:
                post["created_at"] = now_jakarta().isoformat(timespec="minutes")
                items.insert(0, post)
            else:
                items[existing_index] = post
            store.save(content)
        return redirect(url_for("admin", tab="news", saved="1"))

    @app.post("/admin/berita/<slug>/hapus")
    def admin_news_delete(slug):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin"))
        validate_csrf()
        with content_lock:
            content = load_content()
            original_count = len(content.get("news", []))
            content["news"] = [item for item in content.get("news", []) if item.get("slug") != slug]
            if len(content["news"]) == original_count:
                abort(404)
            store.save(content)
        return redirect(url_for("admin", tab="news", saved="1"))

    @app.post("/admin/upload-image")
    def admin_upload_image():
        if not session.get("admin_authenticated"):
            return jsonify(error="Sesi admin telah berakhir. Silakan masuk kembali."), 401
        validate_csrf()
        folder = request.form.get("folder", "site").strip()
        credentials = {
            "cloud_name": app.config.get("CLOUDINARY_CLOUD_NAME"),
            "api_key": app.config.get("CLOUDINARY_API_KEY"),
            "api_secret": app.config.get("CLOUDINARY_API_SECRET"),
        }
        try:
            uploaded = upload_image(request.files.get("image_file"), credentials, folder)
        except CloudinaryConfigurationError as exc:
            return jsonify(error=str(exc)), 503
        except (InvalidImageUpload, ValueError) as exc:
            return jsonify(error=str(exc)), 400
        except Exception as exc:
            detail = _redacted_error_detail(exc, credentials.values())
            app.logger.error("Cloudinary upload failed (%s): %s", folder, detail)
            return jsonify(error="Cloudinary gagal memproses upload. Periksa log server untuk detail tanpa kredensial."), 502
        return jsonify(url=uploaded["url"], public_id=uploaded["public_id"])

    @app.get("/admin/galeri/baru")
    def admin_gallery_new():

        if not session.get("admin_authenticated"):
            return redirect(url_for("admin"))
        return render_admin_gallery_form(
            {
                "id": "",
                "title": "",
                "caption": "",
                "category": "Kegiatan",
                "image": "",
                "image_alt": "",
                "shape": "large",
                "position": "center",
            },
            is_edit=False,
        )

    @app.get("/admin/galeri/<item_id>/edit")
    def admin_gallery_edit(item_id):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin"))
        with content_lock:
            content = load_content()
            if _ensure_gallery_ids(content):
                store.save(content)
            item = next((entry for entry in content.get("gallery", []) if entry.get("id") == item_id), None)
        if item is None:
            abort(404)
        return render_admin_gallery_form(item, is_edit=True)

    @app.post("/admin/galeri/simpan")
    def admin_gallery_save():
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin"))
        validate_csrf()
        original_id = request.form.get("original_id", "").strip()
        is_edit = bool(original_id)
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "Kegiatan").strip()
        caption = request.form.get("caption", "").strip()
        image_alt = request.form.get("image_alt", "").strip()
        shape = request.form.get("shape", "large").strip()
        position = request.form.get("position", "center").strip()
        form_item = {
            "id": original_id,
            "title": title,
            "caption": caption,
            "category": category,
            "image": "",
            "image_alt": image_alt or title,
            "shape": shape,
            "position": position,
        }
        error = None

        with content_lock:
            content = load_content()
            if _ensure_gallery_ids(content):
                store.save(content)
            items = content.setdefault("gallery", [])
            existing_index = next(
                (index for index, entry in enumerate(items) if entry.get("id") == original_id),
                None,
            ) if original_id else None
            if original_id and existing_index is None:
                abort(404)
            existing = items[existing_index] if existing_index is not None else {}
            existing_image = existing.get("image", "")
            form_item["image"] = _safe_image_url(request.form.get("image", ""), existing_image)

            if not title:
                error = "Judul foto wajib diisi."
            submitted_image = request.form.get("image", "").strip()
            if (
                not error
                and submitted_image
                and form_item["image"] == existing_image
                and submitted_image != existing_image
            ):
                error = "Masukkan URL Cloudinary yang valid atau unggah foto melalui tombol Upload."
            elif not error and not form_item["image"]:
                error = "Upload foto ke Cloudinary atau isi URL foto Cloudinary terlebih dahulu."

            if not error:
                if category not in {"Kegiatan", "Santri", "Pesantren"}:
                    category = "Kegiatan"
                if shape not in {"large", "wide", "small"}:
                    shape = "large"
                if position not in {"center", "top", "bottom", "left", "right"}:
                    position = "center"
                form_item.update({
                    "id": existing.get("id") or secrets.token_urlsafe(12),
                    "title": title,
                    "caption": caption,
                    "category": category,
                    "image_alt": image_alt or title,
                    "shape": shape,
                    "position": position,
                })
                if existing_index is None:
                    items.insert(0, form_item)
                else:
                    items[existing_index] = form_item
                store.save(content)

        if error:
            return render_admin_gallery_form(form_item, is_edit=is_edit, error=error, status_code=400)
        return redirect(url_for("admin", tab="gallery", saved="1"))

    @app.post("/admin/galeri/<item_id>/hapus")
    def admin_gallery_delete(item_id):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin"))
        validate_csrf()
        with content_lock:
            content = load_content()
            if _ensure_gallery_ids(content):
                store.save(content)
            items = content.setdefault("gallery", [])
            item = next((entry for entry in items if entry.get("id") == item_id), None)
            if item is None:
                abort(404)
            content["gallery"] = [entry for entry in items if entry.get("id") != item_id]
            store.save(content)
        return redirect(url_for("admin", tab="gallery", saved="1"))

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
