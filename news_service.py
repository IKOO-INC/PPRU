"""News ordering, date helpers, and rich-text sanitization."""
from copy import deepcopy
from datetime import datetime
from html import escape, unescape
import re
from zoneinfo import ZoneInfo

import bleach


JAKARTA = ZoneInfo("Asia/Jakarta")
INDONESIAN_MONTHS = (
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
)
RICH_TEXT_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "h2", "h3", "h4",
    "ul", "ol", "li", "blockquote", "a", "div",
}
RICH_TEXT_ATTRIBUTES = {"a": ["href", "title"]}
RICH_TEXT_PROTOCOLS = ["http", "https", "mailto"]


def sanitize_rich_text(value: str) -> str:
    """Allow only basic article formatting and safe links from the admin editor."""
    return bleach.clean(
        value or "",
        tags=RICH_TEXT_TAGS,
        attributes=RICH_TEXT_ATTRIBUTES,
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
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", clean))).strip()


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
        if post.get("published_at"):
            post["date"] = format_indonesian_date(published_at_value(post))
    result["news"] = visible
    return result
