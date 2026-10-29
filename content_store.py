"""JSON-backed storage for portal preferences, news, and gallery data."""
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _atomic_write_json(file_path: Path, value: Any) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(value, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, file_path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


class JsonContentStore:
    """Read and safely persist one JSON object document."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)

    def load(self) -> dict[str, Any]:
        """Read the latest object from disk."""
        with self.file_path.open("r", encoding="utf-8") as content_file:
            content = json.load(content_file)
        if not isinstance(content, dict):
            raise ValueError(f"The JSON root in {self.file_path.name} must be an object.")
        return content

    def save(self, content: dict[str, Any]) -> None:
        """Atomically replace this JSON object document."""
        if not isinstance(content, dict):
            raise ValueError("The content JSON root must be an object.")
        _atomic_write_json(self.file_path, content)


class JsonListStore:
    """Read and safely persist a JSON array document."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)

    def load(self) -> list[Any]:
        with self.file_path.open("r", encoding="utf-8") as content_file:
            content = json.load(content_file)
        if not isinstance(content, list):
            raise ValueError(f"The JSON root in {self.file_path.name} must be an array.")
        return content

    def save(self, items: list[Any]) -> None:
        if not isinstance(items, list):
            raise ValueError(f"The JSON data for {self.file_path.name} must be an array.")
        _atomic_write_json(self.file_path, items)


class JsonPortalStore:
    """Expose a merged portal document while persisting its three sections separately.

    Older versions kept news and gallery arrays inside preferences.json. On first
    load, those legacy arrays are moved to their dedicated files and removed from
    the preferences document. Existing dedicated files are used after migration.
    """

    def __init__(
        self,
        preferences_file: str | Path,
        news_file: str | Path,
        gallery_file: str | Path,
        seed_preferences_file: str | Path,
        seed_news_file: str | Path,
        seed_gallery_file: str | Path,
    ):
        self.preferences = JsonContentStore(preferences_file)
        self.news = JsonListStore(news_file)
        self.gallery = JsonListStore(gallery_file)
        self.seed_preferences = JsonContentStore(seed_preferences_file)
        self.seed_news = JsonListStore(seed_news_file)
        self.seed_gallery = JsonListStore(seed_gallery_file)

    @staticmethod
    def _load_section(target: JsonListStore, seed: JsonListStore, legacy_items, has_legacy: bool):
        if has_legacy:
            items = legacy_items if isinstance(legacy_items, list) else []
            target.save(items)
            return items
        if target.file_path.exists():
            return target.load()
        try:
            items = seed.load()
        except FileNotFoundError:
            items = []
        target.save(items)
        return items

    def load(self) -> dict[str, Any]:
        preferences_missing = False
        try:
            preferences = self.preferences.load()
        except FileNotFoundError:
            preferences = self.seed_preferences.load()
            preferences_missing = True

        has_legacy_news = "news" in preferences
        has_legacy_gallery = "gallery" in preferences
        legacy_news = preferences.pop("news", None)
        legacy_gallery = preferences.pop("gallery", None)
        news = self._load_section(self.news, self.seed_news, legacy_news, has_legacy_news)
        gallery = self._load_section(self.gallery, self.seed_gallery, legacy_gallery, has_legacy_gallery)

        if preferences_missing or has_legacy_news or has_legacy_gallery:
            self.preferences.save(preferences)

        return {**preferences, "news": news, "gallery": gallery}

    def save(self, content: dict[str, Any]) -> None:
        """Persist news/gallery arrays to their files and all other keys to preferences."""
        if not isinstance(content, dict):
            raise ValueError("The portal content root must be an object.")
        preferences = {key: value for key, value in content.items() if key not in {"news", "gallery"}}
        self.news.save(content.get("news", []))
        self.gallery.save(content.get("gallery", []))
        self.preferences.save(preferences)
