"""Flask application for the PPRU public portal and MongoDB-backed admin."""
import copy
import hmac
import json
import os
import re
import secrets
import threading
from datetime import date
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, quote_plus, urlsplit, urlunsplit

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

from cloudinary_service import CloudinaryConfigurationError, InvalidImageUpload, upload_image
from content_store import (
    JsonPortalStore,
    PersistentStorageError,
    PersistentStorageMirrorUnavailable,
    MongoPortalStore,
    ReadOnlyPortalStore,
)
from nadzom_service import build_book_catalog, load_book
from news_service import (
    INDONESIAN_MONTHS,
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
    ("profile", "Profil & Sejarah"),
    ("news", "Berita"),
    ("works", "Karya Santri"),
    ("gallery", "Galeri"),
    ("events", "Agenda"),
    ("faq", "FAQ"),
    ("contact", "Kontak"),
    ("admission", "PSB"),
    ("hafalan", "Sambung Nadzom"),
    ("users", "Kelola User Admin"),
)
ADMIN_COMPONENT_IDS = {component_id for component_id, _ in ADMIN_COMPONENTS}
ADMIN_CONTENT_COMPONENT_IDS = ADMIN_COMPONENT_IDS - {"users"}
ACADEMIC_PROGRAM_TYPE_LABELS = {
    "formal": "Pendidikan Formal",
    "non_formal": "Pendidikan Non Formal",
}
ACADEMIC_PROGRAM_ICON_OPTIONS = {
    "quran": "Al-Qur’an",
    "school": "Sekolah",
    "book": "Buku",
    "book-open-reader": "Pembaca",
    "graduation-cap": "Pendidikan",
    "chalkboard-user": "Pengajar",
    "scroll": "Kitab",
}
ACADEMIC_PROGRAM_TYPE_SLUGS = {
    "formal": "formal",
    "non_formal": "non-formal",
}
PROFILE_CONTENT_REVISION = "musyawarah-profil-2026-v2"
ACADEMIC_PROGRAM_DETAILS_REVISION = "madrasah-diniyah-details-2026-v2"
CONTACT_ADDRESS_REVISION = "contact-address-2026-v1"
HOME_STATS_REVISION = "home-stats-santri-alumni-2026-v1"
SOCIAL_LINKS_REVISION = "official-social-links-2026-v1"
SOCIAL_PLATFORMS = ("facebook", "instagram", "youtube", "tiktok")
PROFILE_PROGRAM_ALIASES = {
    "Pendidikan Formal SMP & SMK": {"SPM (Muadalah)"},
    "Madrasah Diniyah": {"Diniyah Takmiliyah"},
    "Takhassus Tahfidzul Qur’an": {"Tahfidzul Qur’an"},
}
ADMIN_PREVIEW_PAGES = {
    "brand": ("index.html", "home", "/"),
    "navigation": ("index.html", "home", "/"),
    "hero": ("index.html", "home", "/"),
    "stats": ("index.html", "home", "/"),
    "profile": ("profile.html", "profile", "/profil"),
    "news": ("news.html", "news", "/berita"),
    "works": ("index.html", "home", "/"),
    "gallery": ("gallery.html", "gallery", "/galeri"),
    "events": ("index.html", "home", "/"),
    "faq": ("index.html", "home", "/"),
    "contact": ("contact.html", "contact", "/kontak"),
    "admission": ("admission.html", "admission", "/psb"),
    "hafalan": ("hafalan.html", "hafalan", "/hafalan"),
    "users": ("index.html", "home", "/"),
}


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


def _safe_program_logo(value):
    """Accept only optimized Cloudinary image URLs for uploaded program logos."""
    candidate = str(value or "").strip()
    return _safe_image_url(candidate, "")


def _youtube_embed_url(value, current=""):
    """Normalize trusted YouTube links to a privacy-enhanced embed URL."""
    candidate = str(value or "").strip()
    current = str(current or "")
    if not candidate:
        return ""
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        return current

    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or port not in (None, 443)
    ):
        return current

    video_id = ""
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com"}:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 2 and parts[0] == "embed":
            video_id = parts[1]
        elif parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
    elif host == "youtu.be":
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            video_id = parts[0]

    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return current
    return f"https://www.youtube-nocookie.com/embed/{video_id}"


def _split_paragraphs(value):
    """Split history text on blank lines, treating single line breaks as spaces."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return [
        " ".join(paragraph.split())
        for paragraph in re.split(r"\n[ \t]*\n+", text)
        if paragraph.strip()
    ]


def _split_list_lines(value):
    """Read a one-item-per-line list, also accepting comma separated entries."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    entries = []
    seen = set()
    for line in text.split("\n"):
        for item in line.split(","):
            value = item.strip().lstrip("•-* ").strip()
            if value and value.casefold() not in seen:
                entries.append(value)
                seen.add(value.casefold())
    return entries


def _split_numbered_lines(value):
    """Parse one mission statement per line, stripping optional typed numbering."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    entries = []
    for line in text.split("\n"):
        item = re.sub(r"^\s*(?:\d+[.)-]|[•*-])\s*", "", line).strip()
        if item:
            entries.append(item)
    return entries


def _safe_public_link(value, current="/kontak"):
    """Allow an internal path or an HTTPS information link, never script URLs."""
    candidate = str(value or "").strip()
    fallback = str(current or "/kontak")
    if not candidate:
        return fallback
    if candidate.startswith("/"):
        if candidate.startswith("//") or "\\" in candidate or any(ord(char) < 32 for char in candidate):
            return fallback
        return candidate
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        return fallback
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or any(ord(char) < 32 for char in candidate)
    ):
        return fallback
    return candidate


def _safe_social_url(value, current=""):
    """Accept a blank social profile or a valid HTTPS URL without credentials."""
    candidate = str(value or "").strip()
    fallback = str(current or "")
    if not candidate:
        return ""
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        return fallback
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or any(ord(char) < 32 for char in candidate)
    ):
        return fallback
    return candidate[:500]


def _google_maps_urls(address):
    """Build no-key Google Maps search and embed URLs from the current address."""
    query = str(address or "").strip().rstrip(".").strip()
    if not query:
        return "", ""
    encoded_query = quote_plus(query)
    return (
        f"https://www.google.com/maps?q={encoded_query}&output=embed",
        f"https://www.google.com/maps/search/?api=1&query={encoded_query}",
    )


def _without_admin_users(content):
    """Keep private credential hashes out of all rendered page contexts."""
    return {key: value for key, value in content.items() if key != "admin_users"}


def _academic_item_id(item, index):
    return str(item.get("id") or item.get("number") or index)


def _normalize_academic_program_type(value, category=""):
    """Normalize legacy and current program types to formal/non-formal buckets."""
    for candidate in (value, category):
        normalized = str(candidate or "").strip().casefold().replace("_", " ").replace("-", " ")
        words = normalized.split()
        if "nonformal" in words or ("non" in words and "formal" in words):
            return "non_formal"
        if "formal" in words:
            return "formal"
    return "non_formal"


def _academic_date_label(value):
    try:
        parsed = date.fromisoformat(str(value or ""))
    except (TypeError, ValueError):
        return str(value or "Tanggal belum ditentukan")
    return f"{parsed.day} {INDONESIAN_MONTHS[parsed.month - 1]} {parsed.year}"


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
        social_links = site.get("social_links")
        if not isinstance(social_links, dict):
            social_links = {}
        for platform in SOCIAL_PLATFORMS:
            field_name = f"social_{platform}"
            if field_name in form:
                social_links[platform] = _safe_social_url(
                    form.get(field_name, ""),
                    social_links.get(platform, ""),
                )
        site["social_links"] = social_links

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

    elif component == "profile":
        profile = content.setdefault("profile", {})
        history = content.setdefault("history", {})
        for key in ("title", "subtitle", "history_title", "vision_title", "vision", "leadership_title"):
            profile[key] = _form_value(form, f"profile_{key}", profile.get(key, ""))
        profile["leadership_note"] = _form_value(
            form,
            "profile_leadership_note",
            profile.get("leadership_note", ""),
        )
        history_text = _form_value(
            form,
            "history_paragraphs",
            "\n\n".join(profile.get("history_paragraphs", [])),
        )
        profile["history_paragraphs"] = _split_paragraphs(history_text)
        profile["video_embed_url"] = _youtube_embed_url(
            _form_value(form, "video_embed_url", profile.get("video_embed_url", "")),
            profile.get("video_embed_url", ""),
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
        mission_items = profile.get("mission", [])
        if not isinstance(mission_items, list):
            mission_items = _split_numbered_lines(mission_items)
            profile["mission"] = mission_items
        if "profile_mission_items" in form:
            profile["mission"] = _split_numbered_lines(form.get("profile_mission_items", ""))
        else:
            for index, mission in enumerate(mission_items):
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
        site["address"] = contact.get("address", "")

    elif component == "admission":
        admission = content.setdefault("admission", {})
        for key in ("title", "description", "eyebrow"):
            admission[key] = _form_value(form, f"admission_{key}", admission.get(key, ""))
        admission["image"] = _safe_image_url(
            _form_value(form, "admission_image", admission.get("image", "")),
            admission.get("image", ""),
        )
        admission.pop("programs", None)
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


def _normalize_profile_program_title(value):
    normalized = str(value or "").casefold().replace("’", "'").replace("‘", "'")
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def _merge_profile_programs(current_programs, seed_programs):
    """Refresh profile-owned program copy while retaining admin IDs, logos and extra entries."""
    current_programs = current_programs if isinstance(current_programs, list) else []
    if not isinstance(seed_programs, list):
        return current_programs

    consumed = set()
    merged = []
    for seed_program in seed_programs:
        if not isinstance(seed_program, dict):
            continue
        seed_title = str(seed_program.get("title", ""))
        aliases = PROFILE_PROGRAM_ALIASES.get(seed_title, set())
        match_titles = {_normalize_profile_program_title(seed_title)}
        match_titles.update(_normalize_profile_program_title(alias) for alias in aliases)
        match_index = next(
            (
                index for index, old_program in enumerate(current_programs)
                if index not in consumed
                and isinstance(old_program, dict)
                and _normalize_profile_program_title(old_program.get("title")) in match_titles
            ),
            None,
        )
        updated_program = copy.deepcopy(seed_program)
        if match_index is not None:
            existing = current_programs[match_index]
            consumed.add(match_index)
            for key in ("id", "number", "color", "icon", "logo", "info_url", "class_details"):
                if key in existing and existing[key] not in (None, ""):
                    updated_program[key] = copy.deepcopy(existing[key])
        merged.append(updated_program)

    for index, old_program in enumerate(current_programs):
        if index not in consumed and isinstance(old_program, dict):
            merged.append(copy.deepcopy(old_program))
    for index, program in enumerate(merged, start=1):
        if not program.get("id"):
            program["id"] = secrets.token_urlsafe(10)
        program.setdefault("number", f"{index:02d}")
    return merged


def _apply_profile_content_revision(content, seed_content):
    """Apply the supplied institutional profile copy once, preserving user-managed media."""
    if not isinstance(content, dict) or not isinstance(seed_content, dict):
        return False
    if content.get("_profile_content_revision") == PROFILE_CONTENT_REVISION:
        return False

    section_fields = {
        "site": ("description", "footer_note", "address"),
        "hero": ("eyebrow", "title", "description", "image_note", "image_alt"),
        "history": ("eyebrow", "title", "intro", "body", "quote", "image_alt"),
        "profile": (
            "eyebrow", "title", "subtitle", "history_title", "history_paragraphs",
            "vision_title", "vision", "mission", "leadership_title", "leadership_note",
        ),
        "contact": ("address",),
    }
    for section_name, fields in section_fields.items():
        source = seed_content.get(section_name)
        if not isinstance(source, dict):
            continue
        target = content.setdefault(section_name, {})
        if not isinstance(target, dict):
            target = content[section_name] = {}
        for field in fields:
            if field in source:
                target[field] = copy.deepcopy(source[field])

    for section_name in ("stats", "program_intro"):
        if section_name in seed_content:
            content[section_name] = copy.deepcopy(seed_content[section_name])

    if "programs" in seed_content:
        content["programs"] = _merge_profile_programs(
            content.get("programs"),
            seed_content.get("programs"),
        )

    existing_faq = content.get("faq")
    seed_faq = seed_content.get("faq")
    if isinstance(existing_faq, list) and isinstance(seed_faq, list):
        seed_answers = {
            str(item.get("question", "")).strip(): item.get("answer", "")
            for item in seed_faq if isinstance(item, dict)
        }
        for item in existing_faq:
            if isinstance(item, dict):
                question = str(item.get("question", "")).strip()
                if question in seed_answers:
                    item["answer"] = copy.deepcopy(seed_answers[question])
    elif isinstance(seed_faq, list):
        content["faq"] = copy.deepcopy(seed_faq)

    content["_profile_content_revision"] = PROFILE_CONTENT_REVISION
    return True


def _parse_program_class_details(value):
    """Parse one class per line: name | note/schedule | kitab 1; kitab 2."""
    entries = []
    seen_names = set()
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|", 2)]
        name = parts[0][:120].strip()
        if not name or name.casefold() in seen_names:
            continue
        seen_names.add(name.casefold())
        note = parts[1][:500].strip() if len(parts) > 1 else ""
        kitabs = []
        if len(parts) > 2:
            for item in parts[2].split(";"):
                item = item.strip().lstrip("•-* ").strip()
                if item and item.casefold() not in {entry.casefold() for entry in kitabs}:
                    kitabs.append(item[:160])
        entries.append({
            "name": name,
            "description": note,
            "kitabs_label": "Kitab bandungan",
            "kitabs": kitabs[:30],
        })
        if len(entries) >= 30:
            break
    return entries


def _format_program_class_details(value):
    """Format class details into the editable one-class-per-line admin syntax."""
    lines = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        note = str(item.get("description", "")).strip()
        kitabs = item.get("kitabs", [])
        if not isinstance(kitabs, list):
            kitabs = _split_list_lines(kitabs)
        lines.append(f"{name} | {note} | {'; '.join(str(book).strip() for book in kitabs if str(book).strip())}")
    return "\n".join(lines)


def _apply_academic_program_details_revision(content, seed_content):
    """Seed Madrasah Diniyah details and add the verified senior Syawir end time once."""
    if not isinstance(content, dict) or not isinstance(seed_content, dict):
        return False
    current_revision = content.get("_academic_program_details_revision")
    if current_revision == ACADEMIC_PROGRAM_DETAILS_REVISION:
        return False
    seed_programs = seed_content.get("programs")
    if not isinstance(seed_programs, list):
        return False
    seed_program = next(
        (
            item for item in seed_programs
            if isinstance(item, dict)
            and _normalize_profile_program_title(item.get("title"))
            == _normalize_profile_program_title("Madrasah Diniyah")
        ),
        None,
    )
    if not seed_program:
        return False
    programs = content.get("programs")
    if not isinstance(programs, list):
        return False
    target = next(
        (
            item for item in programs
            if isinstance(item, dict)
            and _normalize_profile_program_title(item.get("title"))
            == _normalize_profile_program_title(seed_program.get("title"))
        ),
        None,
    )
    if target is None:
        return False

    if current_revision == "madrasah-diniyah-details-2026-v1":
        current_details = target.get("class_details")
        if not isinstance(current_details, list):
            current_details = []
            target["class_details"] = current_details
        seeded_details = seed_program.get("class_details", [])
        seeded_by_name = {
            _normalize_profile_program_title(item.get("name")): item
            for item in seeded_details
            if isinstance(item, dict)
        }
        for class_name in ("Tsanawi", "Aliyah"):
            normalized_name = _normalize_profile_program_title(class_name)
            current_item = next(
                (
                    item for item in current_details
                    if isinstance(item, dict)
                    and _normalize_profile_program_title(item.get("name")) == normalized_name
                ),
                None,
            )
            if current_item is None:
                seed_item = seeded_by_name.get(normalized_name)
                if seed_item:
                    current_details.append(copy.deepcopy(seed_item))
                continue
            description = str(current_item.get("description", "")).strip()
            if not re.search(r"\b23[.:]00\b", description):
                schedule = "Syawir dilaksanakan selepas salat Isya hingga pukul 23.00."
                current_item["description"] = (
                    f"{description.rstrip('.; ')}; {schedule}" if description else schedule
                )
    else:
        for field in ("description", "class_details"):
            if field in seed_program:
                target[field] = copy.deepcopy(seed_program[field])

    content["_academic_program_details_revision"] = ACADEMIC_PROGRAM_DETAILS_REVISION
    return True


def _apply_contact_address_revision(content, seed_content):
    """Apply the user-confirmed contact address without replacing other contact data."""
    if not isinstance(content, dict) or not isinstance(seed_content, dict):
        return False
    if content.get("_contact_address_revision") == CONTACT_ADDRESS_REVISION:
        return False
    seed_site = seed_content.get("site")
    seed_contact = seed_content.get("contact")
    address = seed_contact.get("address") if isinstance(seed_contact, dict) else ""
    if not address and isinstance(seed_site, dict):
        address = seed_site.get("address", "")
    if not address:
        return False
    site = content.setdefault("site", {})
    contact = content.setdefault("contact", {})
    if not isinstance(site, dict):
        site = content["site"] = {}
    if not isinstance(contact, dict):
        contact = content["contact"] = {}
    site["address"] = address
    contact["address"] = address
    content["_contact_address_revision"] = CONTACT_ADDRESS_REVISION
    return True


def _apply_home_stats_revision(content, seed_content):
    """Replace the previous homepage counters with the requested four-stat layout once."""
    if not isinstance(content, dict) or not isinstance(seed_content, dict):
        return False
    if content.get("_home_stats_revision") == HOME_STATS_REVISION:
        return False
    seed_stats = seed_content.get("stats")
    if not isinstance(seed_stats, list):
        return False
    content["stats"] = copy.deepcopy(seed_stats)
    content["_home_stats_revision"] = HOME_STATS_REVISION
    return True


def _apply_social_links_revision(content, seed_content):
    """Add the user-supplied official social URLs without replacing admin-managed links."""
    if not isinstance(content, dict) or not isinstance(seed_content, dict):
        return False
    if content.get("_social_links_revision") == SOCIAL_LINKS_REVISION:
        return False
    seed_site = seed_content.get("site")
    seed_links = seed_site.get("social_links") if isinstance(seed_site, dict) else None
    if not isinstance(seed_links, dict):
        return False
    site = content.setdefault("site", {})
    if not isinstance(site, dict):
        site = content["site"] = {}
    current_links = site.get("social_links")
    if not isinstance(current_links, dict):
        current_links = {}
    social_links = copy.deepcopy(current_links)
    for platform in SOCIAL_PLATFORMS:
        official_url = _safe_social_url(seed_links.get(platform, ""))
        current_url = _safe_social_url(social_links.get(platform, ""))
        if official_url and not current_url:
            social_links[platform] = official_url
    site["social_links"] = social_links
    content["_social_links_revision"] = SOCIAL_LINKS_REVISION
    return True


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
        CLOUDINARY_CLOUD_NAME=os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
        CLOUDINARY_API_KEY=os.environ.get("CLOUDINARY_API_KEY", ""),
        CLOUDINARY_API_SECRET=os.environ.get("CLOUDINARY_API_SECRET", ""),
        VERCEL=bool(os.environ.get("VERCEL")),
        VERCEL_ENV=os.environ.get("VERCEL_ENV", "development"),
        MONGODB_URI=os.environ.get("MONGODB_URI", ""),
        MONGODB_DATABASE=os.environ.get("MONGODB_DATABASE", "ppru"),
        MONGODB_COLLECTION=os.environ.get("MONGODB_COLLECTION", "portal_data"),
        MONGODB_NAMESPACE=os.environ.get("MONGODB_NAMESPACE", "ppru"),
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
    store_options = {
        "preferences_file": preferences_file,
        "news_file": news_file,
        "gallery_file": gallery_file,
        "seed_preferences_file": app.config["SEED_CONTENT_FILE"],
        "seed_news_file": app.config["NEWS_SEED_FILE"],
        "seed_gallery_file": app.config["GALLERY_SEED_FILE"],
    }
    mongo_uri = str(app.config.get("MONGODB_URI") or "").strip()
    if mongo_uri:
        storage_environment = str(app.config.get("VERCEL_ENV") or "production").strip()
        storage_namespace = str(app.config.get("MONGODB_NAMESPACE") or "ppru").strip()
        is_vercel = bool(app.config.get("VERCEL"))
        store = MongoPortalStore(
            **store_options,
            mongo_uri=mongo_uri,
            database_name=app.config.get("MONGODB_DATABASE", "ppru"),
            collection_name=app.config.get("MONGODB_COLLECTION", "portal_data"),
            document_id=f"{storage_namespace}:{storage_environment}",
            mirror_json=not is_vercel,
            allow_json_fallback=not is_vercel,
        )
    elif app.config.get("VERCEL"):
        store = ReadOnlyPortalStore(JsonPortalStore(**store_options))
    else:
        store = JsonPortalStore(**store_options)
    try:
        profile_seed_content = json.loads(
            Path(app.config["SEED_CONTENT_FILE"]).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        profile_seed_content = {}
    content_lock = threading.RLock()

    def load_content():
        content = store.load()
        needs_save = _migrate_legacy_hafalan_preferences(content)
        needs_save = _apply_profile_content_revision(content, profile_seed_content) or needs_save
        needs_save = _apply_academic_program_details_revision(content, profile_seed_content) or needs_save
        needs_save = _apply_contact_address_revision(content, profile_seed_content) or needs_save
        needs_save = _apply_home_stats_revision(content, profile_seed_content) or needs_save
        needs_save = _apply_social_links_revision(content, profile_seed_content) or needs_save
        site = content.get("site")
        if isinstance(site, dict):
            if site.get("login_url") in (None, "", "/masuk"):
                site["login_url"] = "https://siapik.com"
                needs_save = True
            if site.get("login_label") in (None, "", "Masuk"):
                site["login_label"] = "Masuk Portal Santri"
                needs_save = True
            stored_social_links = site.get("social_links")
            if stored_social_links is not None:
                social_links = stored_social_links if isinstance(stored_social_links, dict) else {}
                normalized_social_links = {
                    platform: safe_url
                    for platform in SOCIAL_PLATFORMS
                    if (safe_url := _safe_social_url(social_links.get(platform, "")))
                }
                if stored_social_links != normalized_social_links:
                    site["social_links"] = normalized_social_links
                    needs_save = True
        profile = content.get("profile")
        if isinstance(profile, dict):
            profile["video_embed_url"] = _youtube_embed_url(profile.get("video_embed_url", ""))
        programs = content.get("programs")
        if not isinstance(programs, list):
            programs = []
        normalized_programs = []
        for program in programs:
            if not isinstance(program, dict):
                continue
            kitabs = program.get("kitabs", [])
            if not isinstance(kitabs, list):
                kitabs = _split_list_lines(kitabs)
            program["kitabs"] = [str(kitab).strip() for kitab in kitabs if str(kitab).strip()]
            kitabs_label = str(program.get("kitabs_label", "Kitab yang dipelajari") or "Kitab yang dipelajari").strip()
            if program.get("kitabs_label") != kitabs_label or "kitabs_label" not in program:
                program["kitabs_label"] = kitabs_label
                needs_save = True
            raw_class_details = program.get("class_details", [])
            normalized_class_details = []
            if isinstance(raw_class_details, list):
                for class_item in raw_class_details:
                    if not isinstance(class_item, dict):
                        continue
                    class_name = str(class_item.get("name", "")).strip()[:120]
                    if not class_name:
                        continue
                    class_kitabs = class_item.get("kitabs", [])
                    if not isinstance(class_kitabs, list):
                        class_kitabs = _split_list_lines(class_kitabs)
                    normalized_class_details.append({
                        **class_item,
                        "name": class_name,
                        "description": str(class_item.get("description", "")).strip()[:500],
                        "kitabs_label": str(class_item.get("kitabs_label", "Kitab bandungan") or "Kitab bandungan").strip()[:80],
                        "kitabs": [str(book).strip()[:160] for book in class_kitabs if str(book).strip()][:30],
                    })
            if "class_details" in program and program.get("class_details") != normalized_class_details:
                program["class_details"] = normalized_class_details
                needs_save = True
            elif "class_details" not in program and normalized_class_details:
                program["class_details"] = normalized_class_details
                needs_save = True
            program["info_url"] = _safe_public_link(program.get("info_url", "/kontak"))
            logo = _safe_program_logo(program.get("logo", ""))
            if program.get("logo") != logo:
                program["logo"] = logo
                needs_save = True
            icon = str(program.get("icon", "book") or "book").strip()
            if icon not in ACADEMIC_PROGRAM_ICON_OPTIONS:
                icon = "book"
            if program.get("icon") != icon:
                program["icon"] = icon
                needs_save = True
            education_type = _normalize_academic_program_type(
                program.get("education_type"),
                program.get("category", ""),
            )
            if program.get("education_type") != education_type:
                program["education_type"] = education_type
                needs_save = True
            normalized_programs.append(program)
        content["programs"] = normalized_programs
        academic_events = content.get("academic_events")
        if not isinstance(academic_events, list):
            academic_events = []
        content["academic_events"] = [event for event in academic_events if isinstance(event, dict)]
        if needs_save and not isinstance(store, ReadOnlyPortalStore):
            store.save(content)
        return content

    def admin_storage_context():
        if isinstance(store, MongoPortalStore):
            fallback = bool(store.json_fallback_active)
            return {
                "storage_backend": "json-fallback" if fallback else "mongodb",
                "storage_fallback": fallback,
                "storage_json_mirror": bool(store.mirror_json),
            }
        if isinstance(store, ReadOnlyPortalStore):
            return {
                "storage_backend": "read-only",
                "storage_fallback": False,
                "storage_json_mirror": False,
            }
        return {
            "storage_backend": "json",
            "storage_fallback": False,
            "storage_json_mirror": False,
        }

    def page_context(active_page, **extra):
        content = _without_admin_users(public_content(load_content()))
        for program in content.get("programs", []):
            if isinstance(program, dict) and program.get("class_details"):
                program["detail_url"] = f"/akademik/program/{slugify(program.get('title', ''))}"
        contact = content.get("contact") if isinstance(content.get("contact"), dict) else {}
        site = content.get("site") if isinstance(content.get("site"), dict) else {}
        map_embed_url, map_search_url = _google_maps_urls(
            contact.get("address") or site.get("address", "")
        )
        return {
            "site": site,
            "data": content,
            "active_page": active_page,
            "map_embed_url": map_embed_url,
            "map_search_url": map_search_url,
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

    def current_admin_role():
        if not session.get("admin_authenticated"):
            return None
        # Treat older authenticated sessions without a role as the main administrator.
        return session.get("admin_role", "main")

    def is_main_admin():
        return current_admin_role() == "main"

    def require_main_admin():
        role = current_admin_role()
        if role is None:
            return redirect(url_for("admin"))
        if role != "main":
            abort(403)
        return None

    def require_academic_admin():
        role = current_admin_role()
        if role is None:
            return redirect(url_for("admin"))
        if role not in {"main", "academic"}:
            abort(403)
        if role == "academic":
            users = load_content().get("admin_users", {})
            account = users.get("academic", {}) if isinstance(users, dict) else {}
            if not isinstance(account, dict):
                account = {}
            saved_token = str(account.get("session_token", ""))
            session_token = str(session.get("admin_token", ""))
            if not account.get("active") or not saved_token or not session_token or not hmac.compare_digest(saved_token, session_token):
                session.clear()
                return redirect(url_for("admin"))
        return None

    def render_admin_news_form(post, is_edit, error=None, status_code=200, academic=False):
        content = load_content()
        visible_content = _without_admin_users(content)
        body_html = post.get("body_html") or legacy_article_html(post)
        return render_template(
            "admin_news_form.html",
            site=visible_content.get("site", {}),
            data=visible_content,
            active_page=None,
            post=post,
            editor_html=Markup(sanitize_rich_text(body_html)),
            published_at_input=to_local_input(post.get("published_at")),
            is_edit=is_edit,
            error=error,
            academic=academic,
            form_action=url_for("admin_academic_announcement_save" if academic else "admin_news_save"),
            cancel_url=url_for("admin_academic", tab="announcements") if academic else url_for("admin", tab="news"),
        ), status_code

    def render_admin_gallery_form(item, is_edit, error=None, status_code=200):
        content = _without_admin_users(load_content())
        return render_template(
            "admin_gallery_form.html",
            site=content.get("site", {}),
            data=content,
            active_page=None,
            item=item,
            is_edit=is_edit,
            error=error,
        ), status_code

    def save_news_entry(academic=False):
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
            if academic and existing and not existing.get("academic"):
                abort(404)
            title = request.form.get("title", "").strip()
            submitted_image = request.form.get("image", "").strip()
            existing_image = existing.get("image", "")
            image_url = _safe_image_url(submitted_image, existing_image)
            form_error = None
            if not title:
                form_error = "Judul pengumuman wajib diisi." if academic else "Judul berita wajib diisi."
            elif not image_url:
                form_error = "Upload foto cover ke Cloudinary atau masukkan URL Cloudinary."
            elif submitted_image and image_url == existing_image and submitted_image != existing_image:
                form_error = "URL foto harus menggunakan HTTPS Cloudinary atau gunakan tombol Upload."
            if form_error:
                post = {
                    **existing,
                    "slug": request.form.get("slug", "").strip(),
                    "title": title,
                    "category": request.form.get("category", "Pengumuman Akademik" if academic else "Kegiatan").strip(),
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
                    academic=academic,
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
                "category": request.form.get("category", "Pengumuman Akademik" if academic else "Kegiatan").strip() or ("Pengumuman Akademik" if academic else "Kegiatan"),
                "excerpt": excerpt,
                "date": format_indonesian_date(published_at),
                "published_at": published_at.isoformat(timespec="minutes"),
                "status": status,
                "views": _view_count(existing),
                "image": image_url,
                "image_alt": request.form.get("image_alt", "").strip() or title,
                "body_html": body_html,
                "updated_at": now_jakarta().isoformat(timespec="minutes"),
                "academic": True if academic else bool(existing.get("academic")),
            }
            if not existing:
                post["created_at"] = now_jakarta().isoformat(timespec="minutes")
                items.insert(0, post)
            else:
                items[existing_index] = post
            store.save(content)
        if academic:
            return redirect(url_for("admin_academic", tab="announcements", saved="1"))
        return redirect(url_for("admin", tab="news", saved="1"))

    app.jinja_env.globals["csrf_token"] = csrf_value

    def academic_page_context(selected_education_type=None):
        context = page_context("programs", selected_education_type=selected_education_type)
        all_programs = context["data"].get("programs", [])
        context["education_groups"] = [
            {
                "key": education_type,
                "slug": ACADEMIC_PROGRAM_TYPE_SLUGS[education_type],
                "label": label,
                "programs": [
                    program for program in all_programs
                    if _normalize_academic_program_type(program.get("education_type")) == education_type
                ],
            }
            for education_type, label in ACADEMIC_PROGRAM_TYPE_LABELS.items()
            if selected_education_type is None or education_type == selected_education_type
        ]
        context["education_type_counts"] = {
            education_type: sum(
                1 for program in all_programs
                if _normalize_academic_program_type(program.get("education_type")) == education_type
            )
            for education_type in ACADEMIC_PROGRAM_TYPE_LABELS
        }
        context["selected_education_type_label"] = ACADEMIC_PROGRAM_TYPE_LABELS.get(selected_education_type, "")
        calendar_events = context["data"].get("academic_events", [])
        calendar_events.sort(key=lambda item: str(item.get("date", "9999-12-31")))
        for item in calendar_events:
            item["date_label"] = _academic_date_label(item.get("date"))
        return context

    @app.get("/")
    def home():
        context = page_context("home")
        today = now_jakarta().date()
        upcoming_events = []
        for event in context["data"].get("academic_events", []):
            try:
                event_date = date.fromisoformat(str(event.get("date", "")))
            except (TypeError, ValueError):
                continue
            if event_date < today:
                continue
            upcoming_events.append((
                event_date,
                {
                    **event,
                    "day": f"{event_date.day:02d}",
                    "month": INDONESIAN_MONTHS[event_date.month - 1][:3],
                },
            ))
        context["data"]["academic_events"] = [
            event for _, event in sorted(upcoming_events, key=lambda item: item[0])[:3]
        ]
        return render_template("index.html", **context)

    @app.get("/profil")
    def profile():
        return render_template("profile.html", **page_context("profile"))

    @app.get("/akademik")
    @app.get("/program")
    def programs():
        return render_template("programs.html", **academic_page_context())

    @app.get("/akademik/<education_type_slug>")
    def academic_programs_by_type(education_type_slug):
        selected_education_type = next(
            (
                education_type
                for education_type, slug in ACADEMIC_PROGRAM_TYPE_SLUGS.items()
                if slug == education_type_slug
            ),
            None,
        )
        if selected_education_type is None:
            abort(404)
        return render_template(
            "programs.html",
            **academic_page_context(selected_education_type=selected_education_type),
        )

    @app.get("/akademik/program/<program_slug>")
    def academic_program_detail(program_slug):
        context = page_context("programs")
        program = next(
            (
                item for item in context["data"].get("programs", [])
                if isinstance(item, dict)
                and slugify(item.get("title", "")) == program_slug
                and item.get("class_details")
            ),
            None,
        )
        if program is None:
            abort(404)
        education_type = _normalize_academic_program_type(program.get("education_type"), program.get("category", ""))
        context["program"] = program
        context["education_type_label"] = ACADEMIC_PROGRAM_TYPE_LABELS[education_type]
        context["back_url"] = f"/akademik/{ACADEMIC_PROGRAM_TYPE_SLUGS[education_type]}"
        return render_template("academic_program_detail.html", **context)

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
            content = _without_admin_users(public_content(content))

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
        role = current_admin_role()
        if role == "academic":
            return redirect(url_for("admin_academic"))
        if role is not None and role != "main":
            session.clear()
            role = None
        content = load_content()
        visible_content = _without_admin_users(content)
        if role is None:
            return render_template(
                "admin_login.html",
                site=visible_content.get("site", {}),
                data=visible_content,
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
        stored_admin_users = content.get("admin_users", {})
        academic_account = stored_admin_users.get("academic", {}) if isinstance(stored_admin_users, dict) else {}
        if not isinstance(academic_account, dict):
            academic_account = {}
        academic_admin_view = {
            "username": academic_account.get("username", ""),
            "active": bool(academic_account.get("active")),
            "password_hash": bool(academic_account.get("password_hash")),
        }
        visible_content = _without_admin_users(content)
        history_paragraphs = content.get("profile", {}).get("history_paragraphs", [])
        if not isinstance(history_paragraphs, list):
            history_paragraphs = [str(history_paragraphs)] if history_paragraphs else []
        return render_template(
            "admin.html",
            site=visible_content.get("site", {}),
            data=visible_content,
            active_page=None,
            components=ADMIN_COMPONENTS,
            active_component=component,
            preview_path=ADMIN_PREVIEW_PAGES[component][2],
            history_text="\n\n".join(history_paragraphs),
            saved=request.args.get("saved") == "1",
            news_items=news_items,
            gallery_items=content.get("gallery", []),
            academic_admin=academic_admin_view,
            user_error=request.args.get("user_error", ""),
            **admin_storage_context(),
        )

    @app.post("/admin/live-preview")
    def admin_live_preview():
        if not is_main_admin():
            abort(401 if current_admin_role() is None else 403)
        validate_csrf()
        component = request.form.get("component", "")
        if component not in ADMIN_PREVIEW_PAGES:
            abort(400, description="Komponen preview tidak dikenal.")

        content = load_content()
        _apply_admin_form(content, request.form, component)
        template_name, active_page, _preview_path = ADMIN_PREVIEW_PAGES[component]
        preview_data = _without_admin_users(public_content(content))
        template_context = {
            "site": preview_data.get("site", {}),
            "data": preview_data,
            "active_page": active_page,
        }
        if component == "hafalan":
            template_context["book_catalog"] = build_book_catalog()
        return render_template(template_name, **template_context)

    @app.get("/admin/berita/baru")
    def admin_news_new():
        access_response = require_main_admin()
        if access_response is not None:
            return access_response
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
        access_response = require_main_admin()
        if access_response is not None:
            return access_response
        content = load_content()
        post = next((item for item in content.get("news", []) if item.get("slug") == slug), None)
        if post is None:
            abort(404)
        return render_admin_news_form(post, is_edit=True)

    @app.post("/admin/berita/simpan")
    def admin_news_save():
        access_response = require_main_admin()
        if access_response is not None:
            return access_response
        return save_news_entry(academic=False)

    @app.post("/admin/berita/<slug>/hapus")
    def admin_news_delete(slug):
        access_response = require_main_admin()
        if access_response is not None:
            return access_response
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

        access_response = require_main_admin()
        if access_response is not None:
            return access_response
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
        access_response = require_main_admin()
        if access_response is not None:
            return access_response
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
        access_response = require_main_admin()
        if access_response is not None:
            return access_response
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
        access_response = require_main_admin()
        if access_response is not None:
            return access_response
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

    @app.post("/admin/users/save")
    def admin_users_save():
        access_response = require_main_admin()
        if access_response is not None:
            return access_response
        validate_csrf()
        content = load_content()
        users = content.get("admin_users")
        if not isinstance(users, dict):
            users = {}
            content["admin_users"] = users
        existing = users.get("academic", {})
        if not isinstance(existing, dict):
            existing = {}
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        active = request.form.get("active") == "1"

        error = ""
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", username):
            error = "Nama pengguna harus 3–64 karakter dan hanya berisi huruf, angka, titik, garis bawah, atau tanda hubung."
        elif password and len(password) < 12:
            error = "Kata sandi admin akademik minimal 12 karakter."
        elif password and password != password_confirm:
            error = "Konfirmasi kata sandi tidak cocok."
        elif active and not (password or existing.get("password_hash")):
            error = "Tetapkan kata sandi sebelum mengaktifkan akun admin akademik."
        if error:
            return redirect(url_for("admin", tab="users", user_error=error))

        account = {
            **existing,
            "username": username,
            "active": active,
            "session_token": secrets.token_urlsafe(32),
            "updated_at": now_jakarta().isoformat(timespec="minutes"),
        }
        if password:
            account["password_hash"] = generate_password_hash(password)
        users["academic"] = account
        store.save(content)
        return redirect(url_for("admin", tab="users", saved="1"))

    @app.get("/admin/akademik")
    def admin_academic():
        access_response = require_academic_admin()
        if access_response is not None:
            return access_response
        content = load_content()
        tab = request.args.get("tab", "formal")
        if tab == "programs":
            tab = "formal"
        if tab not in {"formal", "non_formal", "calendar", "announcements"}:
            tab = "formal"
        programs = content.get("programs", [])
        academic_events = sorted(
            content.get("academic_events", []),
            key=lambda item: str(item.get("date", "9999-12-31")),
        )
        announcements = sorted(
            [item for item in content.get("news", []) if item.get("academic")],
            key=published_at_value,
            reverse=True,
        )
        program_items = [
            {**program, "admin_id": _academic_item_id(program, index)}
            for index, program in enumerate(programs)
            if _normalize_academic_program_type(program.get("education_type")) == tab
        ] if tab in ACADEMIC_PROGRAM_TYPE_LABELS else []
        education_type_counts = {
            education_type: sum(
                1 for program in programs
                if _normalize_academic_program_type(program.get("education_type")) == education_type
            )
            for education_type in ACADEMIC_PROGRAM_TYPE_LABELS
        }
        event_items = [
            {**item, "admin_id": _academic_item_id(item, index), "date_label": _academic_date_label(item.get("date"))}
            for index, item in enumerate(academic_events)
        ]
        return render_template(
            "admin_academic.html",
            site=content.get("site", {}),
            data=_without_admin_users(content),
            tab=tab,
            programs=program_items,
            education_type_counts=education_type_counts,
            education_type_labels=ACADEMIC_PROGRAM_TYPE_LABELS,
            academic_events=event_items,
            announcements=announcements,
            saved=request.args.get("saved") == "1",
            admin_username=session.get("admin_username", "Admin Akademik"),
            **admin_storage_context(),
        )

    @app.get("/admin/akademik/program/baru")
    def admin_academic_program_new():
        access_response = require_academic_admin()
        if access_response is not None:
            return access_response
        content = _without_admin_users(load_content())
        education_type = request.args.get("education_type", "formal")
        if education_type not in ACADEMIC_PROGRAM_TYPE_LABELS:
            education_type = "formal"
        return render_template(
            "admin_academic_program_form.html",
            site=content.get("site", {}),
            data=content,
            item={
                "title": "",
                "category": "Program pendidikan",
                "description": "",
                "kitabs_label": "Materi utama",
                "kitabs": [],
                "class_details": [],
                "class_details_text": "",
                "info_url": "/kontak",
                "education_type": education_type,
                "icon": "book",
                "logo": "",
            },
            item_id="",
            icon_options=ACADEMIC_PROGRAM_ICON_OPTIONS,
            error=None,
        )

    @app.get("/admin/akademik/program/<item_id>/edit")
    def admin_academic_program_edit(item_id):
        access_response = require_academic_admin()
        if access_response is not None:
            return access_response
        content = load_content()
        programs = content.get("programs", [])
        found = next(
            ((index, item) for index, item in enumerate(programs) if _academic_item_id(item, index) == item_id),
            None,
        )
        if found is None:
            abort(404)
        index, item = found
        item = {**item, "class_details_text": _format_program_class_details(item.get("class_details", []))}
        return render_template(
            "admin_academic_program_form.html",
            site=content.get("site", {}),
            data=_without_admin_users(content),
            item=item,
            item_id=_academic_item_id(item, index),
            icon_options=ACADEMIC_PROGRAM_ICON_OPTIONS,
            error=None,
        )

    @app.post("/admin/akademik/program/simpan")
    def admin_academic_program_save():
        access_response = require_academic_admin()
        if access_response is not None:
            return access_response
        validate_csrf()
        item_id = request.form.get("item_id", "").strip()
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "Program pendidikan").strip() or "Program pendidikan"
        description = request.form.get("description", "").strip()
        kitabs = _split_list_lines(request.form.get("kitabs", ""))
        kitabs_label_field_provided = "kitabs_label" in request.form
        kitabs_label = request.form.get("kitabs_label", "").strip() or "Kitab yang dipelajari"
        class_details_field_provided = "class_details" in request.form
        class_details_text = request.form.get("class_details", "")
        class_details = _parse_program_class_details(class_details_text)
        submitted_education_type = request.form.get("education_type", "").strip()
        education_type = (
            submitted_education_type
            if submitted_education_type in ACADEMIC_PROGRAM_TYPE_LABELS
            else _normalize_academic_program_type("", category)
        )
        submitted_info_url = request.form.get("info_url", "").strip()
        info_url = _safe_public_link(submitted_info_url)
        icon_field_provided = "icon" in request.form
        icon = request.form.get("icon", "").strip() or "book"
        logo_field_provided = "program_logo" in request.form
        submitted_logo = request.form.get("program_logo", "").strip()
        logo = _safe_program_logo(submitted_logo)
        error = None
        if not title:
            error = "Judul kelas/program wajib diisi."
        elif not description:
            error = "Keterangan program wajib diisi."
        elif not kitabs:
            error = "Tambahkan minimal satu kitab, materi, atau jenjang program."
        elif submitted_education_type and submitted_education_type not in ACADEMIC_PROGRAM_TYPE_LABELS:
            error = "Pilih Pendidikan Formal atau Pendidikan Non Formal."
        elif icon_field_provided and icon not in ACADEMIC_PROGRAM_ICON_OPTIONS:
            error = "Pilih ikon Font Awesome yang tersedia."
        elif submitted_logo and not logo:
            error = "Logo harus berupa URL gambar Cloudinary HTTPS yang valid."
        elif submitted_info_url and info_url == "/kontak" and submitted_info_url != "/kontak":
            error = "Tautan informasi harus berupa path lokal atau URL HTTPS yang valid."

        item = {
            "id": item_id,
            "title": title,
            "category": category,
            "education_type": education_type,
            "description": description,
            "kitabs_label": kitabs_label,
            "kitabs": kitabs,
            "class_details": class_details,
            "info_url": info_url,
            "icon": icon,
            "logo": logo,
        }
        if error:
            page_content = _without_admin_users(load_content())
            return render_template(
                "admin_academic_program_form.html",
                site=page_content.get("site", {}),
                data=page_content,
                item={**item, "class_details_text": class_details_text},
                item_id=item_id,
                icon_options=ACADEMIC_PROGRAM_ICON_OPTIONS,
                error=error,
            ), 400

        with content_lock:
            content = load_content()
            programs = content.setdefault("programs", [])
            existing_index = next(
                (index for index, entry in enumerate(programs) if item_id and _academic_item_id(entry, index) == item_id),
                None,
            )
            if item_id and existing_index is None:
                abort(404)
            existing = programs[existing_index] if existing_index is not None else {}
            if existing_index is not None and not kitabs_label_field_provided:
                item["kitabs_label"] = existing.get("kitabs_label", "Kitab yang dipelajari")
            if existing_index is not None and not class_details_field_provided:
                item["class_details"] = existing.get("class_details", [])
            if existing_index is not None and not icon_field_provided:
                item["icon"] = existing.get("icon", "book")
            if existing_index is not None and not logo_field_provided:
                item["logo"] = existing.get("logo", "")
            if not submitted_education_type and existing_index is not None:
                education_type = _normalize_academic_program_type(
                    existing.get("education_type"),
                    existing.get("category", category),
                )
                item["education_type"] = education_type
            item.update({
                "id": existing.get("id") or secrets.token_urlsafe(10),
                "number": existing.get("number") or f"{len(programs) + 1:02d}",
                "color": existing.get("color", "green"),
            })
            if existing_index is None:
                programs.append(item)
            else:
                programs[existing_index] = item
            store.save(content)
        return redirect(url_for("admin_academic", tab=education_type, saved="1"))

    @app.post("/admin/akademik/program/<item_id>/hapus")
    def admin_academic_program_delete(item_id):
        access_response = require_academic_admin()
        if access_response is not None:
            return access_response
        validate_csrf()
        with content_lock:
            content = load_content()
            programs = content.setdefault("programs", [])
            existing_index = next(
                (index for index, entry in enumerate(programs) if _academic_item_id(entry, index) == item_id),
                None,
            )
            if existing_index is None:
                abort(404)
            deleted_type = _normalize_academic_program_type(programs[existing_index].get("education_type"))
            programs.pop(existing_index)
            store.save(content)
        return redirect(url_for("admin_academic", tab=deleted_type, saved="1"))

    @app.get("/admin/akademik/kalender/baru")
    def admin_academic_calendar_new():
        access_response = require_academic_admin()
        if access_response is not None:
            return access_response
        content = _without_admin_users(load_content())
        return render_template(
            "admin_academic_calendar_form.html",
            site=content.get("site", {}),
            data=content,
            item={"date": "", "title": "", "category": "Akademik", "description": ""},
            item_id="",
            error=None,
        )

    @app.get("/admin/akademik/kalender/<item_id>/edit")
    def admin_academic_calendar_edit(item_id):
        access_response = require_academic_admin()
        if access_response is not None:
            return access_response
        content = load_content()
        events = content.get("academic_events", [])
        found = next(
            ((index, item) for index, item in enumerate(events) if _academic_item_id(item, index) == item_id),
            None,
        )
        if found is None:
            abort(404)
        index, item = found
        return render_template(
            "admin_academic_calendar_form.html",
            site=content.get("site", {}),
            data=_without_admin_users(content),
            item=item,
            item_id=_academic_item_id(item, index),
            error=None,
        )

    @app.post("/admin/akademik/kalender/simpan")
    def admin_academic_calendar_save():
        access_response = require_academic_admin()
        if access_response is not None:
            return access_response
        validate_csrf()
        item_id = request.form.get("item_id", "").strip()
        date_value = request.form.get("date", "").strip()
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "Akademik").strip() or "Akademik"
        description = request.form.get("description", "").strip()
        try:
            date.fromisoformat(date_value)
        except ValueError:
            date_value = ""
        error = None
        if not date_value:
            error = "Tanggal kalender wajib diisi."
        elif not title:
            error = "Nama kegiatan akademik wajib diisi."
        item = {"id": item_id, "date": date_value, "title": title, "category": category, "description": description}
        if error:
            page_content = _without_admin_users(load_content())
            return render_template(
                "admin_academic_calendar_form.html",
                site=page_content.get("site", {}),
                data=page_content,
                item=item,
                item_id=item_id,
                error=error,
            ), 400

        with content_lock:
            content = load_content()
            events = content.setdefault("academic_events", [])
            existing_index = next(
                (index for index, entry in enumerate(events) if item_id and _academic_item_id(entry, index) == item_id),
                None,
            )
            if item_id and existing_index is None:
                abort(404)
            existing = events[existing_index] if existing_index is not None else {}
            item["id"] = existing.get("id") or secrets.token_urlsafe(10)
            if existing_index is None:
                events.append(item)
            else:
                events[existing_index] = item
            store.save(content)
        return redirect(url_for("admin_academic", tab="calendar", saved="1"))

    @app.post("/admin/akademik/kalender/<item_id>/hapus")
    def admin_academic_calendar_delete(item_id):
        access_response = require_academic_admin()
        if access_response is not None:
            return access_response
        validate_csrf()
        with content_lock:
            content = load_content()
            events = content.setdefault("academic_events", [])
            existing_index = next(
                (index for index, entry in enumerate(events) if _academic_item_id(entry, index) == item_id),
                None,
            )
            if existing_index is None:
                abort(404)
            events.pop(existing_index)
            store.save(content)
        return redirect(url_for("admin_academic", tab="calendar", saved="1"))

    @app.get("/admin/akademik/pengumuman/baru")
    def admin_academic_announcement_new():
        access_response = require_academic_admin()
        if access_response is not None:
            return access_response
        post = {
            "slug": "", "title": "", "category": "Pengumuman Akademik", "excerpt": "",
            "image": "", "image_alt": "", "status": "published", "views": 0, "body_html": "",
        }
        return render_admin_news_form(post, is_edit=False, academic=True)

    @app.get("/admin/akademik/pengumuman/<slug>/edit")
    def admin_academic_announcement_edit(slug):
        access_response = require_academic_admin()
        if access_response is not None:
            return access_response
        content = load_content()
        post = next(
            (item for item in content.get("news", []) if item.get("slug") == slug and item.get("academic")),
            None,
        )
        if post is None:
            abort(404)
        return render_admin_news_form(post, is_edit=True, academic=True)

    @app.post("/admin/akademik/pengumuman/simpan")
    def admin_academic_announcement_save():
        access_response = require_academic_admin()
        if access_response is not None:
            return access_response
        return save_news_entry(academic=True)

    @app.post("/admin/akademik/pengumuman/<slug>/hapus")
    def admin_academic_announcement_delete(slug):
        access_response = require_academic_admin()
        if access_response is not None:
            return access_response
        validate_csrf()
        with content_lock:
            content = load_content()
            items = content.setdefault("news", [])
            index = next(
                (index for index, item in enumerate(items) if item.get("slug") == slug and item.get("academic")),
                None,
            )
            if index is None:
                abort(404)
            items.pop(index)
            store.save(content)
        return redirect(url_for("admin_academic", tab="announcements", saved="1"))

    @app.post("/admin/login")
    def admin_login():
        content = load_content()
        visible_content = _without_admin_users(content)
        validate_csrf()
        entered_password = request.form.get("password", "")
        entered_username = request.form.get("username", "").strip()
        admin_password = str(app.config["ADMIN_PASSWORD"])
        main_matches = bool(entered_password) and hmac.compare_digest(entered_password, admin_password)
        stored_admin_users = content.get("admin_users", {})
        academic_account = stored_admin_users.get("academic", {}) if isinstance(stored_admin_users, dict) else {}
        academic_matches = False
        password_hash = academic_account.get("password_hash") if isinstance(academic_account, dict) else None
        username_matches = (
            bool(entered_username)
            and entered_username.casefold() == str(academic_account.get("username", "")).casefold()
            if isinstance(academic_account, dict)
            else False
        )
        if not main_matches and username_matches and entered_password and password_hash and academic_account.get("active"):
            try:
                academic_matches = check_password_hash(password_hash, entered_password)
            except (TypeError, ValueError):
                academic_matches = False
        if not main_matches and not academic_matches:
            return render_template(
                "admin_login.html",
                site=visible_content.get("site", {}),
                data=visible_content,
                active_page=None,
                error="Kata sandi admin tidak sesuai.",
            ), 401
        session.clear()
        session["admin_authenticated"] = True
        session["admin_role"] = "main" if main_matches else "academic"
        session["admin_username"] = "Admin Utama" if main_matches else academic_account.get("username", "Admin Akademik")
        if academic_matches:
            session["admin_token"] = str(academic_account.get("session_token", ""))
        csrf_value()
        if academic_matches:
            return redirect(url_for("admin_academic"))
        return redirect(url_for("admin"))

    @app.post("/admin/save")
    def admin_save():
        access_response = require_main_admin()
        if access_response is not None:
            return access_response
        validate_csrf()
        component = request.form.get("component", "")
        if component not in ADMIN_CONTENT_COMPONENT_IDS:
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

    @app.errorhandler(PersistentStorageError)
    def persistent_storage_error(error):
        app.logger.warning("Portal persistent storage unavailable (%s)", type(error).__name__)
        mirror_saved = isinstance(error, PersistentStorageMirrorUnavailable)
        return render_template(
            "storage_error.html",
            message=error.user_message,
            title="MongoDB Atlas berhasil menyimpan" if mirror_saved else "Perubahan belum dapat disimpan",
            data_saved=mirror_saved,
        ), 503

    return app


app = create_app()

if __name__ == "__main__":
    # 0.0.0.0 makes the development server accessible in the preview environment.
    app.run(host="0.0.0.0", port=5000, debug=True)
