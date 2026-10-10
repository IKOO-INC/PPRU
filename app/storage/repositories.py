"""Repository berbasis JSON array.

Setiap item punya field `id` (integer, auto-increment). Method yang dipakai
view: all, get, create, update, delete. Versi MongoDB nanti cukup
meniru antarmuka ini.
"""
from datetime import datetime
from pathlib import Path

from .json_store import LOCK, read_json, write_json


def _now():
    return datetime.now().isoformat(timespec="seconds")


class JsonListRepository:
    def __init__(self, path):
        self.path = Path(path)

    def _load(self):
        return read_json(self.path, [])

    def all(self):
        return self._load()

    def get(self, item_id):
        try:
            item_id = int(item_id)
        except (TypeError, ValueError):
            return None
        for item in self._load():
            if item.get("id") == item_id:
                return item
        return None

    def create(self, data):
        with LOCK:
            items = self._load()
            next_id = max((i.get("id", 0) for i in items), default=0) + 1
            item = {"id": next_id, **data, "dibuat": _now(), "diubah": _now()}
            items.append(item)
            write_json(self.path, items)
            return item

    def update(self, item_id, data):
        with LOCK:
            items = self._load()
            for item in items:
                if item.get("id") == int(item_id):
                    item.update(data)
                    item["diubah"] = _now()
                    write_json(self.path, items)
                    return item
            return None

    def delete(self, item_id):
        with LOCK:
            items = self._load()
            kept = [i for i in items if i.get("id") != int(item_id)]
            if len(kept) == len(items):
                return False
            write_json(self.path, kept)
            return True


class BeritaRepository(JsonListRepository):
    def published(self, kategori=None, limit=None):
        items = [i for i in self.all() if i.get("status") == "publish"]
        if kategori:
            items = [i for i in items if i.get("kategori") == kategori]
        items.sort(key=lambda i: (i.get("tanggal", ""), i["id"]), reverse=True)
        return items[:limit] if limit else items

    def get_published_by_slug(self, slug):
        for item in self.published():
            if item.get("slug") == slug:
                return item
        return None

    def slug_taken(self, slug, exclude_id=None):
        return any(
            i.get("slug") == slug and i.get("id") != exclude_id for i in self.all()
        )


class GalleryRepository(JsonListRepository):
    def latest(self, limit=None):
        items = sorted(self.all(), key=lambda i: i["id"], reverse=True)
        return items[:limit] if limit else items


class SettingsRepository:
    """Satu file JSON berisi objek per bagian situs (identitas, hero, dst.)."""

    def __init__(self, path, defaults):
        self.path = Path(path)
        self.defaults = defaults

    def ensure_file(self):
        with LOCK:
            if not self.path.exists():
                write_json(self.path, self.defaults)

    def all(self):
        data = read_json(self.path, {})
        merged = {}
        for key, default in self.defaults.items():
            merged[key] = data.get(key, default)
        return merged

    def section(self, name):
        return self.all()[name]

    def save_section(self, name, value):
        with LOCK:
            data = self.all()
            data[name] = value
            write_json(self.path, data)


class AdminRepository:
    def __init__(self, path):
        self.path = Path(path)

    def get(self):
        if not self.path.exists():
            return None
        return read_json(self.path, None)

    def save(self, username, password_hash):
        with LOCK:
            write_json(self.path, {"username": username, "password_hash": password_hash})
