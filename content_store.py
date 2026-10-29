"""JSON-backed storage for portal preferences, news, and gallery data."""
import json
import os
import tempfile
import urllib.error
import urllib.request
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


class PersistentStorageError(RuntimeError):
    """Base class for deployment storage errors that should not become HTTP 500s."""

    user_message = "Penyimpanan data sedang tidak tersedia. Silakan coba kembali."


class PersistentStorageNotConfigured(PersistentStorageError):
    """Raised when a serverless deployment has no durable writable data store."""

    user_message = (
        "Perubahan admin belum dapat disimpan karena Vercel tidak menyediakan penyimpanan "
        "file persisten. Hubungkan Upstash Redis ke project Vercel agar "
        "KV_REST_API_URL dan KV_REST_API_TOKEN tersedia, lalu deploy ulang. "
        "Data belum diubah."
    )


class PersistentStorageUnavailable(PersistentStorageError):
    """Raised when the configured remote key-value service cannot be used."""

    user_message = (
        "Penyimpanan data sedang tidak dapat dihubungi. Perubahan belum tersimpan; "
        "periksa koneksi Upstash Redis dan coba kembali."
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


class UpstashRestClient:
    """Small Redis REST client using only the Python standard library."""

    def __init__(self, url: str, token: str, timeout: float = 8.0):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def command(self, *parts: str) -> Any:
        if not self.url.startswith("https://"):
            raise PersistentStorageUnavailable()
        body = json.dumps(list(parts), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            # Never surface the request headers/token or provider response to users/logs.
            raise PersistentStorageUnavailable() from None
        if not isinstance(payload, dict) or payload.get("error"):
            raise PersistentStorageUnavailable()
        return payload.get("result")


class UpstashJsonPortalStore(JsonPortalStore):
    """Persist the portal's three JSON sections in Upstash Redis via REST commands."""

    def __init__(
        self,
        preferences_file: str | Path,
        news_file: str | Path,
        gallery_file: str | Path,
        seed_preferences_file: str | Path,
        seed_news_file: str | Path,
        seed_gallery_file: str | Path,
        rest_url: str,
        rest_token: str,
        key_prefix: str,
    ):
        super().__init__(
            preferences_file=preferences_file,
            news_file=news_file,
            gallery_file=gallery_file,
            seed_preferences_file=seed_preferences_file,
            seed_news_file=seed_news_file,
            seed_gallery_file=seed_gallery_file,
        )
        self.client = UpstashRestClient(rest_url, rest_token)
        self.key_prefix = key_prefix.strip(":") or "ppru:production"

    def _key(self, section: str) -> str:
        return f"{self.key_prefix}:{section}"

    def _get_json(self, section: str) -> Any:
        value = self.client.command("GET", self._key(section))
        if value is None:
            return None
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            raise PersistentStorageUnavailable() from None

    def _seed_list(self, seed: JsonListStore) -> list[Any]:
        try:
            return seed.load()
        except FileNotFoundError:
            return []

    def load(self) -> dict[str, Any]:
        preferences = self._get_json("preferensi")
        preferences_missing = preferences is None
        if preferences_missing:
            preferences = self.seed_preferences.load()
        if not isinstance(preferences, dict):
            raise ValueError("The preferences data in persistent storage must be an object.")

        has_legacy_news = "news" in preferences
        has_legacy_gallery = "gallery" in preferences
        legacy_news = preferences.pop("news", None)
        legacy_gallery = preferences.pop("gallery", None)

        remote_news = None if has_legacy_news else self._get_json("berita")
        news_missing = remote_news is None
        if has_legacy_news:
            news = legacy_news if isinstance(legacy_news, list) else []
        elif news_missing:
            news = self._seed_list(self.seed_news)
        else:
            news = remote_news
        if not isinstance(news, list):
            raise ValueError("The news data in persistent storage must be an array.")

        remote_gallery = None if has_legacy_gallery else self._get_json("galeri")
        gallery_missing = remote_gallery is None
        if has_legacy_gallery:
            gallery = legacy_gallery if isinstance(legacy_gallery, list) else []
        elif gallery_missing:
            gallery = self._seed_list(self.seed_gallery)
        else:
            gallery = remote_gallery
        if not isinstance(gallery, list):
            raise ValueError("The gallery data in persistent storage must be an array.")

        if (
            preferences_missing
            or has_legacy_news
            or has_legacy_gallery
            or news_missing
            or gallery_missing
        ):
            self.save({**preferences, "news": news, "gallery": gallery})

        return {**preferences, "news": news, "gallery": gallery}

    def save(self, content: dict[str, Any]) -> None:
        if not isinstance(content, dict):
            raise ValueError("The portal content root must be an object.")
        news = content.get("news", [])
        gallery = content.get("gallery", [])
        if not isinstance(news, list) or not isinstance(gallery, list):
            raise ValueError("The portal news and gallery data must be arrays.")
        preferences = {key: value for key, value in content.items() if key not in {"news", "gallery"}}
        command = ["MSET"]
        for section, value in (
            ("preferensi", preferences),
            ("berita", news),
            ("galeri", gallery),
        ):
            command.extend((self._key(section), json.dumps(value, ensure_ascii=False, separators=(",", ":"))))
        if self.client.command(*command) != "OK":
            raise PersistentStorageUnavailable()
