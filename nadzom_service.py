"""Read and describe the Alfiyah and Imrity nadzom question banks."""
import json
from collections import Counter
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent / "data"
BOOKS = {
    "alfiyah": {"title": "Alfiyah Ibnu Malik", "filename": "alfiyah.json"},
    "imrity": {"title": "Imrity", "filename": "imrity.json"},
}
REQUIRED_FIELDS = ("id", "bab", "syathr1", "syathr2")


def load_book(book_id: str, data_dir: str | Path = DATA_DIR) -> list[dict] | None:
    """Load one allow-listed JSON array; return None for unknown book IDs."""
    book = BOOKS.get(book_id)
    if book is None:
        return None

    path = Path(data_dir) / book["filename"]
    with path.open("r", encoding="utf-8") as source:
        records = json.load(source)
    if not isinstance(records, list):
        raise ValueError(f"Data nadzom {path.name} harus berupa JSON array.")
    if any(not isinstance(row, dict) or any(not row.get(field) for field in REQUIRED_FIELDS) for row in records):
        raise ValueError(f"Ada bait nadzom dengan field wajib yang kosong di {path.name}.")
    return records


def _chapter_runs(records: list[dict]) -> list[dict]:
    """Preserve chapter order and separate repeated chapter names into distinct ranges."""
    chapters = []
    for row_index, row in enumerate(records):
        chapter_name = str(row["bab"]).strip()
        if chapters and chapters[-1]["name"] == chapter_name:
            chapters[-1]["end_index"] = row_index
            chapters[-1]["last_id"] = row["id"]
            chapters[-1]["count"] += 1
        else:
            chapters.append({
                "index": len(chapters),
                "name": chapter_name,
                "label": chapter_name,
                "start_index": row_index,
                "end_index": row_index,
                "first_id": row["id"],
                "last_id": row["id"],
                "count": 1,
            })

    name_counts = Counter(chapter["name"] for chapter in chapters)
    name_positions = Counter()
    for chapter in chapters:
        if name_counts[chapter["name"]] > 1:
            name_positions[chapter["name"]] += 1
            chapter["label"] = f"{chapter['name']} (bagian {name_positions[chapter['name']]})"
    return chapters


def build_book_catalog(data_dir: str | Path = DATA_DIR) -> list[dict]:
    """Return small book/chapter metadata for the setup form, not the full poem arrays."""
    catalog = []
    for book_id, book in BOOKS.items():
        records = load_book(book_id, data_dir)
        if not records:
            raise ValueError(f"Bank nadzom untuk {book['title']} kosong.")
        catalog.append({
            "id": book_id,
            "title": book["title"],
            "count": len(records),
            "chapters": _chapter_runs(records),
        })
    return catalog
