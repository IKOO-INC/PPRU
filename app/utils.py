import re
import unicodedata
from datetime import date, datetime

BULAN_SINGKAT = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
BULAN_PANJANG = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember",
]


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def format_tanggal(value, short=False):
    d = _to_date(value)
    if d is None:
        return value or ""
    bulan = BULAN_SINGKAT[d.month - 1] if short else BULAN_PANJANG[d.month - 1]
    return f"{d.day} {bulan} {d.year}"


def tanggal_harian(value):
    """Mengembalikan (hari, bulan singkat) untuk kotak tanggal agenda."""
    d = _to_date(value)
    if d is None:
        return "", ""
    return f"{d.day:02d}", BULAN_SINGKAT[d.month - 1]


def slugify(text, max_length=80):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:max_length].rstrip("-") or "berita"


def unique_slug(base, is_taken):
    slug, n = base, 2
    while is_taken(slug):
        slug = f"{base}-{n}"
        n += 1
    return slug


def paragraphs(text):
    """Pecah teks per baris (baris kosong dibuang)."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]
