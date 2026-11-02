"""Private, durable storage for completed Hafalan challenge results."""
from copy import deepcopy
import threading
from pathlib import Path
from typing import Any

from pymongo.errors import PyMongoError

from content_store import (
    JsonListStore,
    MongoPortalStore,
    PersistentStorageError,
    PersistentStorageNotConfigured,
    PersistentStorageUnavailable,
    ReadOnlyPortalStore,
)


class HafalanResultStore:
    """Store participation records separately from public portal content."""

    def __init__(self, portal_store, file_path: str | Path, lock=None):
        self.portal_store = portal_store
        self.file_store = JsonListStore(file_path)
        self.lock = lock or threading.RLock()

    def _mongo_collection(self):
        return self.portal_store._get_collection().database["hafalan_results"]

    def _read_json(self) -> list[dict[str, Any]]:
        try:
            records = self.file_store.load()
        except FileNotFoundError:
            return []
        except (OSError, ValueError):
            raise PersistentStorageUnavailable() from None
        if not isinstance(records, list):
            raise PersistentStorageUnavailable()
        return [record for record in records if isinstance(record, dict)]

    def _append_json(self, record: dict[str, Any]) -> None:
        with self.lock:
            records = self._read_json()
            records.append(deepcopy(record))
            try:
                self.file_store.save(records)
            except (OSError, ValueError):
                raise PersistentStorageUnavailable() from None

    def save_result(self, record: dict[str, Any]) -> bool:
        """Save a result and return whether it had to use temporary local fallback."""
        if isinstance(self.portal_store, ReadOnlyPortalStore):
            raise PersistentStorageNotConfigured()

        if isinstance(self.portal_store, MongoPortalStore):
            if self.portal_store.json_fallback_active:
                self._append_json(record)
                return True
            document = {**record, "scope": self.portal_store.document_id}
            try:
                result = self._mongo_collection().insert_one(document)
            except (PyMongoError, PersistentStorageError) as error:
                if not self.portal_store.allow_json_fallback:
                    if isinstance(error, PersistentStorageError):
                        raise error
                    raise PersistentStorageUnavailable() from None
                self._append_json(record)
                self.portal_store.json_fallback_active = True
                return True
            if not getattr(result, "acknowledged", True):
                raise PersistentStorageUnavailable()
            return False

        self._append_json(record)
        return False

    def list_results(self) -> list[dict[str, Any]]:
        if isinstance(self.portal_store, ReadOnlyPortalStore):
            raise PersistentStorageNotConfigured()

        if isinstance(self.portal_store, MongoPortalStore):
            if self.portal_store.json_fallback_active:
                return self._read_json()
            try:
                cursor = self._mongo_collection().find(
                    {"scope": self.portal_store.document_id},
                    {"_id": 0, "scope": 0},
                ).sort("completed_at", -1)
                return [record for record in cursor if isinstance(record, dict)]
            except (PyMongoError, PersistentStorageError) as error:
                if not self.portal_store.allow_json_fallback:
                    if isinstance(error, PersistentStorageError):
                        raise error
                    raise PersistentStorageUnavailable() from None
                self.portal_store.json_fallback_active = True
                return self._read_json()

        return self._read_json()
