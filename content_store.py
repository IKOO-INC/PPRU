"""JSON-backed content/preferences storage used by the Flask routes."""
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class JsonContentStore:
    """Read and safely persist the complete portal settings JSON document."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)

    def load(self) -> dict[str, Any]:
        """Read the latest content from disk (useful while editing preferences)."""
        with self.file_path.open("r", encoding="utf-8") as content_file:
            content = json.load(content_file)
        if not isinstance(content, dict):
            raise ValueError("The content JSON root must be an object.")
        return content

    def save(self, content: dict[str, Any]) -> None:
        """Atomically replace the JSON file so interrupted writes do not corrupt it."""
        if not isinstance(content, dict):
            raise ValueError("The content JSON root must be an object.")
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.file_path.parent,
                prefix=f".{self.file_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(content, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.file_path)
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()
