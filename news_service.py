"""News ordering, date helpers, and rich-text sanitization."""
from copy import deepcopy
from datetime import datetime
from html import escape, unescape
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import bleach


JAKARTA = ZoneInfo("Asia/Jakarta")
INDONESIAN_MONTHS = (
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
)
RICH_TEXT_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "h2", "h3", "h4",
    "ul", "ol", "li", "blockquote", "a", "div", "img",
}
RICH_TEXT_PROTOCOLS = ["http", "https", "mailto"]
NEWS_SUMMARY_MAX_CHARS = 160


def _trusted_news_image_url(value: str) -> bool:
    """Allow inserted article images only from Cloudinary's HTTPS image delivery path."""
    candidate = str(value or "").strip()
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        return False
    path_parts = [part for part in parsed.path.split("/") if part]
    return (
        parsed.scheme == "https"
        and parsed.hostname == "res.cloudinary.com"
        and not parsed.username
        and not parsed.password
        and port in (None, 443)
        and len(path_parts) >= 4
        and path_parts[1:3] == ["image", "upload"]
    )


def _rich_text_attribute_allowed(tag: str, name: str, value: str) -> bool:
    if tag == "a":
        return name in {"href", "title"}
    if tag == "p" and name == "class":
        return value == "article-image"
    if tag == "img":
        if name == "src":
            return _trusted_news_image_url(value)
        if name == "alt":
            return len(value) <= 300
        if name == "loading":
            return value == "lazy"
    return False


def sanitize_rich_text(value: str) -> str:
    """Allow basic formatting and responsive Cloudinary images, stripping unsafe markup."""
    source = re.sub(
        r"<\s*(script|style)\b[^>]*>.*?<\s*/\s*\1\s*>",
        "",
        value or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    return bleach.clean(
        source,
        tags=RICH_TEXT_TAGS,
        attributes=_rich_text_attribute_allowed,
        protocols=RICH_TEXT_PROTOCOLS,
        strip=True,
    ).strip()


def legacy_article_html(post: dict) -> str:
    """Convert the earlier heading/paragraph JSON shape into safe editor HTML."""
    blocks = []
    for section in post.get("content", []):
        heading = escape(str(section.get("heading", "")).strip())
        if heading:
            blocks.append(f"<h2>{heading}</h2>")
        for paragraph in section.get("paragraphs", []):
            paragraph = escape(str(paragraph).strip())
            if paragraph:
                blocks.append(f"<p>{paragraph}</p>")
    return sanitize_rich_text("".join(blocks))


def rich_text_plain_text(value: str) -> str:
    clean = sanitize_rich_text(value)
    text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", clean))).strip()
    return re.sub(r"\s+([,.;:!?،؛؟])", r"\1", text)


def news_summary(post: dict, max_chars: int = NEWS_SUMMARY_MAX_CHARS) -> str:
    """Build one consistent card summary from article text, with an ASCII ellipsis on truncation."""
    post = post if isinstance(post, dict) else {}
    body_html = str(post.get("body_html", "") or "")
    summary = rich_text_plain_text(body_html) if body_html else ""
    if not summary:
        legacy_html = legacy_article_html(post)
        summary = rich_text_plain_text(legacy_html) if legacy_html else ""
    if not summary:
        fallback = bleach.clean(str(post.get("excerpt", "") or ""), tags=[], strip=True)
        summary = re.sub(r"\s+", " ", unescape(fallback)).strip()

    try:
        max_chars = max(4, int(max_chars))
    except (TypeError, ValueError):
        max_chars = NEWS_SUMMARY_MAX_CHARS
    if len(summary) <= max_chars:
        return summary

    excerpt = summary[:max_chars - 3]
    if " " in excerpt:
        excerpt = excerpt.rsplit(" ", 1)[0]
    return f"{excerpt.rstrip(' ,;:-')}..."


def slugify(value: str) -> str:
    value = (value or "").lower().strip()
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[\s_-]+", "-", value, flags=re.UNICODE).strip("-")
    return value or "berita-baru"


def now_jakarta() -> datetime:
    return datetime.now(JAKARTA).replace(second=0, microsecond=0)


def parse_local_datetime(value: str | None) -> datetime:
    if not value:
        return now_jakarta()
    try:
        parsed = datetime.fromisoformat(value.strip())
    except (TypeError, ValueError):
        return now_jakarta()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JAKARTA)
    return parsed.astimezone(JAKARTA).replace(second=0, microsecond=0)


def to_local_input(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JAKARTA)
    return parsed.astimezone(JAKARTA).strftime("%Y-%m-%dT%H:%M")


def format_indonesian_date(value: datetime) -> str:
    local = value.astimezone(JAKARTA)
    return f"{local.day:02d} {INDONESIAN_MONTHS[local.month - 1]} {local.year}"


def published_at_value(post: dict) -> datetime:
    for key in ("published_at", "updated_at", "created_at"):
        value = post.get(key)
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=JAKARTA)
        return parsed.astimezone(JAKARTA)
    return datetime.min.replace(tzinfo=JAKARTA)


def public_content(content: dict) -> dict:
    """Return a copy containing only published news, newest first."""
    result = deepcopy(content)
    visible = [
        post for post in result.get("news", [])
        if post.get("status", "published") == "published"
    ]
    visible.sort(key=published_at_value, reverse=True)
    for post in visible:
        post.setdefault("views", 0)
        post["excerpt"] = news_summary(post)
        if post.get("published_at"):
            post["date"] = format_indonesian_date(published_at_value(post))
    result["news"] = visible
    return result
