"""Atlas-primary storage with JSON persistence and local fallback for portal content."""
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from pymongo.errors import PyMongoError


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


class PersistentStorageError(RuntimeError):
    """Base class for deployment storage errors that should not become HTTP 500s."""

    user_message = "Penyimpanan data sedang tidak tersedia. Silakan coba kembali."


class PersistentStorageNotConfigured(PersistentStorageError):
    """Raised when a serverless deployment has no durable writable data store."""

    user_message = (
        "Perubahan admin belum dapat disimpan karena Vercel tidak menyediakan penyimpanan "
        "file persisten. Hubungkan MongoDB Atlas ke project Vercel dan atur "
        "MONGODB_URI, lalu deploy ulang. Data belum diubah."
    )


class PersistentStorageUnavailable(PersistentStorageError):
    """Raised when the configured MongoDB Atlas service cannot be used."""

    user_message = (
        "Penyimpanan MongoDB Atlas sedang tidak dapat dihubungi. Perubahan belum tersimpan; "
        "periksa MONGODB_URI dan aturan Network Access Atlas, lalu coba kembali."
    )


class JsonFallbackUnavailable(PersistentStorageError):
    """Raised when both MongoDB and a writable local JSON fallback are unavailable."""

    user_message = (
        "MongoDB Atlas sedang tidak dapat dihubungi dan preferensi.json lokal tidak dapat "
        "ditulis. Perubahan belum tersimpan."
    )


class PersistentStorageMirrorUnavailable(PersistentStorageError):
    """Raised when Atlas is saved but the optional local JSON mirror cannot be updated."""

    user_message = (
        "MongoDB Atlas berhasil menyimpan perubahan, tetapi mirror JSON lokal gagal "
        "diperbarui. Data utama tetap berada di MongoDB Atlas."
    )


class ReadOnlyPortalStore:
    """Allow reads from bundled JSON files, but never claim Vercel writes succeeded."""

    def __init__(self, file_store: JsonPortalStore):
        self.file_store = file_store

    def load(self) -> dict[str, Any]:
        try:
            return self.file_store.load()
        except OSError:
            # Vercel's deployment bundle is read-only; initialization/migration must
            # use a persistent store rather than attempting to write beside the code.
            raise PersistentStorageNotConfigured() from None

    def save(self, content: dict[str, Any]) -> None:
        raise PersistentStorageNotConfigured()


class MongoPortalStore(JsonPortalStore):
    """Persist portal JSON sections in one atomic MongoDB Atlas document."""

    def __init__(
        self,
        preferences_file: str | Path,
        news_file: str | Path,
        gallery_file: str | Path,
        seed_preferences_file: str | Path,
        seed_news_file: str | Path,
        seed_gallery_file: str | Path,
        mongo_uri: str,
        database_name: str = "ppru",
        collection_name: str = "portal_data",
        document_id: str = "ppru:production",
        mirror_json: bool = True,
        allow_json_fallback: bool = False,
    ):
        super().__init__(
            preferences_file=preferences_file,
            news_file=news_file,
            gallery_file=gallery_file,
            seed_preferences_file=seed_preferences_file,
            seed_news_file=seed_news_file,
            seed_gallery_file=seed_gallery_file,
        )
        self.mongo_uri = str(mongo_uri or "").strip()
        self.database_name = str(database_name or "ppru").strip()
        self.collection_name = str(collection_name or "portal_data").strip()
        self.document_id = str(document_id or "ppru:production").strip()
        self.mirror_json = bool(mirror_json)
        self.allow_json_fallback = bool(allow_json_fallback)
        self.json_fallback_active = False
        self.client = None
        self._collection = None

    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        if not self.mongo_uri:
            raise PersistentStorageNotConfigured()
        if not self.mongo_uri.startswith(("mongodb://", "mongodb+srv://")):
            raise PersistentStorageUnavailable()
        try:
            self.client = MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                appname="PPRU portal",
            )
            self._collection = self.client[self.database_name][self.collection_name]
        except (PyMongoError, ValueError):
            raise PersistentStorageUnavailable() from None
        return self._collection

    def _seed_content(self) -> dict[str, Any]:
        # When Atlas has no document yet, import the current runtime JSON first.
        # Seed files are only a read-only fallback for a new deployment without
        # writable/runtime JSON files.
        try:
            return super().load()
        except OSError:
            pass

        preferences = self.seed_preferences.load()
        if not isinstance(preferences, dict):
            raise PersistentStorageUnavailable()
        legacy_news = preferences.pop("news", None)
        legacy_gallery = preferences.pop("gallery", None)
        news = legacy_news if isinstance(legacy_news, list) else self._seed_list(self.seed_news)
        gallery = legacy_gallery if isinstance(legacy_gallery, list) else self._seed_list(self.seed_gallery)
        return {**preferences, "news": news, "gallery": gallery}

    @staticmethod
    def _seed_list(seed: JsonListStore) -> list[Any]:
        try:
            return seed.load()
        except FileNotFoundError:
            return []

    def _load_json_fallback(self, error: Exception) -> dict[str, Any]:
        if not self.allow_json_fallback:
            if isinstance(error, PersistentStorageError):
                raise error
            raise PersistentStorageUnavailable() from None
        try:
            content = super().load()
        except (OSError, ValueError):
            raise JsonFallbackUnavailable() from None
        self.json_fallback_active = True
        return content

    def _save_json_fallback(self, content: dict[str, Any], error: Exception) -> None:
        if not self.allow_json_fallback:
            if isinstance(error, PersistentStorageError):
                raise error
            raise PersistentStorageUnavailable() from None
        try:
            super().save(content)
        except (OSError, ValueError):
            raise JsonFallbackUnavailable() from None
        self.json_fallback_active = True

    def load(self) -> dict[str, Any]:
        try:
            document = self._get_collection().find_one({"_id": self.document_id})
        except (PyMongoError, PersistentStorageError) as error:
            return self._load_json_fallback(error)

        self.json_fallback_active = False
        if document is None:
            content = self._seed_content()
            self.save(content)
            return content

        preferences = document.get("preferensi")
        if preferences is None:
            preferences = self.seed_preferences.load()
            needs_save = True
        elif not isinstance(preferences, dict):
            raise PersistentStorageUnavailable()
        else:
            needs_save = False

        has_legacy_news = "news" in preferences
        has_legacy_gallery = "gallery" in preferences
        legacy_news = preferences.pop("news", None)
        legacy_gallery = preferences.pop("gallery", None)

        if has_legacy_news:
            news = legacy_news if isinstance(legacy_news, list) else []
            needs_save = True
        else:
            news = document.get("berita")
            if news is None:
                news = self._seed_list(self.seed_news)
                needs_save = True
            elif not isinstance(news, list):
                raise PersistentStorageUnavailable()

        if has_legacy_gallery:
            gallery = legacy_gallery if isinstance(legacy_gallery, list) else []
            needs_save = True
        else:
            gallery = document.get("gallery")
            if gallery is None:
                gallery = self._seed_list(self.seed_gallery)
                needs_save = True
            elif not isinstance(gallery, list):
                raise PersistentStorageUnavailable()

        content = {**preferences, "news": news, "gallery": gallery}
        if needs_save:
            self.save(content)
        return content

    def save(self, content: dict[str, Any]) -> None:
        if not isinstance(content, dict):
            raise ValueError("The portal content root must be an object.")
        news = content.get("news", [])
        gallery = content.get("gallery", [])
        if not isinstance(news, list) or not isinstance(gallery, list):
            raise ValueError("The portal news and gallery data must be arrays.")
        preferences = {key: value for key, value in content.items() if key not in {"news", "gallery"}}
        document = {
            "_id": self.document_id,
            "preferensi": preferences,
            "berita": news,
            "gallery": gallery,
        }
        try:
            result = self._get_collection().replace_one(
                {"_id": self.document_id},
                document,
                upsert=True,
            )
        except (PyMongoError, PersistentStorageError) as error:
            self._save_json_fallback(content, error)
            return
        if not result.acknowledged:
            raise PersistentStorageUnavailable()

        self.json_fallback_active = False
        if self.mirror_json:
            try:
                super().save(content)
            except OSError:
                raise PersistentStorageMirrorUnavailable() from None
