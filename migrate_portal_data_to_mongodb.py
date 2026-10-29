"""Import current JSON portal content and Cloudinary preview URLs into MongoDB Atlas.

Set MONGODB_URI and the Cloudinary credentials in the process environment, then run:
    python migrate_portal_data_to_mongodb.py --environment production

Local JSON files are read only. Local /static image files referenced by the content are
uploaded to Cloudinary, and only their optimized HTTPS delivery URLs are written to Atlas.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from app import _safe_image_url
from cloudinary_service import upload_local_image
from content_store import (
    MongoPortalStore,
    PersistentStorageError,
)


BASE_DIR = Path(__file__).resolve().parent
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
IMAGE_FIELD_NAMES = {
    "image",
    "image_url",
    "logo_path",
    "placeholder_image",
    "map_image",
    "photo",
    "photo_url",
}
REQUIRED_PREVIEW_TRANSFORMS = ("w_1600", "h_1600", "q_auto", "f_auto")


def _read_json(path: Path, expected_type, fallback: Path | None = None):
    source = path if path.is_file() else fallback
    if source is None or not source.is_file():
        raise FileNotFoundError(f"JSON source file is missing: {path.name}")
    with source.open("r", encoding="utf-8") as json_file:
        value = json.load(json_file)
    if not isinstance(value, expected_type):
        raise ValueError(f"Unexpected JSON format in {source.name}.")
    return value


def load_portal_content(root: str | Path = BASE_DIR) -> dict:
    """Read the active local JSON files, falling back to seed JSON when needed."""
    root = Path(root)
    seed_dir = root / "data"
    preferences_path = root / "preferensi.json"
    preferences = _read_json(preferences_path, dict, seed_dir / "site.json")

    has_legacy_news = "news" in preferences
    has_legacy_gallery = "gallery" in preferences
    legacy_news = preferences.pop("news", None)
    legacy_gallery = preferences.pop("gallery", None)

    if has_legacy_news:
        news = legacy_news if isinstance(legacy_news, list) else []
    else:
        news = _read_json(root / "berita.json", list, seed_dir / "berita.json")

    if has_legacy_gallery:
        gallery = legacy_gallery if isinstance(legacy_gallery, list) else []
    else:
        gallery = _read_json(root / "gallery.json", list, seed_dir / "gallery.json")

    return {**preferences, "news": news, "gallery": gallery}


def _collect_local_image_urls(value, found=None) -> set[str]:
    found = found if found is not None else set()
    if isinstance(value, dict):
        for item in value.values():
            _collect_local_image_urls(item, found)
    elif isinstance(value, list):
        for item in value:
            _collect_local_image_urls(item, found)
    elif isinstance(value, str) and value.startswith("/static/"):
        path = value.split("?", 1)[0].split("#", 1)[0]
        if PurePosixPath(path).suffix.lower() in IMAGE_EXTENSIONS:
            found.add(path)
    return found


def _local_image_path(image_url: str, root: str | Path = BASE_DIR) -> Path:
    root = Path(root).resolve()
    static_dir = (root / "static").resolve()
    relative = PurePosixPath(urlsplit(image_url).path).relative_to("/static")
    if ".." in relative.parts:
        raise ValueError(f"Unsafe static image reference: {image_url}")
    local_path = (static_dir / Path(*relative.parts)).resolve()
    if static_dir not in local_path.parents or not local_path.is_file():
        raise FileNotFoundError(f"Image file does not exist inside static/: {image_url}")
    return local_path


def _replace_local_image_urls(value, url_map: dict[str, str]):
    if isinstance(value, dict):
        return {key: _replace_local_image_urls(item, url_map) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_local_image_urls(item, url_map) for item in value]
    if isinstance(value, str) and value.startswith("/static/"):
        bare_url = value.split("?", 1)[0].split("#", 1)[0]
        return url_map.get(bare_url, value)
    return value


def _normalize_cloudinary_urls(value):
    if isinstance(value, dict):
        return {key: _normalize_cloudinary_urls(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_cloudinary_urls(item) for item in value]
    if isinstance(value, str) and value.startswith("https://res.cloudinary.com/"):
        return _safe_image_url(value, value)
    return value


def _is_image_field(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered in IMAGE_FIELD_NAMES
        or lowered.endswith("_image")
        or lowered.endswith("_image_url")
        or lowered.endswith("_photo")
        or lowered.endswith("_photo_url")
    )


def _validate_cloudinary_image_fields(value, path="") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}" if path else key
            if _is_image_field(str(key)) and isinstance(item, str) and item.strip():
                parsed = urlsplit(item.strip())
                if parsed.scheme != "https" or parsed.hostname != "res.cloudinary.com":
                    raise ValueError(f"Image field {item_path} is not a Cloudinary HTTPS URL.")
                if not all(transform in parsed.path for transform in REQUIRED_PREVIEW_TRANSFORMS):
                    raise ValueError(f"Image field {item_path} is missing the optimized Cloudinary preview URL.")
            else:
                _validate_cloudinary_image_fields(item, item_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_cloudinary_image_fields(item, f"{path}[{index}]")


def prepare_portal_content(
    content: dict,
    root: str | Path = BASE_DIR,
    cloudinary_credentials: dict | None = None,
    upload_fn=None,
) -> tuple[dict, dict[str, int]]:
    """Return a Mongo-ready copy, replacing local media paths with Cloudinary previews."""
    if not isinstance(content, dict):
        raise ValueError("Portal content must be a JSON object.")
    upload_fn = upload_fn or upload_local_image
    local_urls = sorted(_collect_local_image_urls(content))
    credentials = cloudinary_credentials or {}
    if local_urls and not all(
        str(credentials.get(key, "")).strip()
        for key in ("cloud_name", "api_key", "api_secret")
    ):
        raise ValueError(
            "Local image assets remain in the JSON data. Configure all three Cloudinary credentials before migration."
        )

    url_map = {}
    uploaded_by_hash = {}
    for image_url in local_urls:
        local_path = _local_image_path(image_url, root)
        digest = hashlib.sha256(local_path.read_bytes()).hexdigest()[:32]
        if digest not in uploaded_by_hash:
            result = upload_fn(
                local_path,
                credentials,
                folder="site",
                public_id=f"portal-{digest}",
            )
            uploaded_url = str(result.get("url", "")).strip()
            preview_url = _safe_image_url(uploaded_url, uploaded_url)
            parsed_preview = urlsplit(preview_url)
            if (
                parsed_preview.scheme != "https"
                or parsed_preview.hostname != "res.cloudinary.com"
                or not all(transform in parsed_preview.path for transform in REQUIRED_PREVIEW_TRANSFORMS)
            ):
                raise ValueError(f"Cloudinary did not return a valid optimized preview for {image_url}.")
            uploaded_by_hash[digest] = preview_url
        url_map[image_url] = uploaded_by_hash[digest]

    migrated = _replace_local_image_urls(content, url_map)
    migrated = _normalize_cloudinary_urls(migrated)
    _validate_cloudinary_image_fields(migrated)
    return migrated, {
        "local_image_urls": len(local_urls),
        "cloudinary_assets": len(uploaded_by_hash),
        "news_items": len(migrated.get("news", [])),
        "gallery_items": len(migrated.get("gallery", [])),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate current PPRU JSON data into MongoDB Atlas.")
    parser.add_argument(
        "--environment",
        default=os.environ.get("VERCEL_ENV") or "production",
        choices=("development", "preview", "production"),
        help="MongoDB document environment (default: production).",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace the destination document if it already exists. Review current Atlas data first.",
    )
    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    mongo_uri = os.environ.get("MONGODB_URI", "").strip()
    if not mongo_uri:
        raise SystemExit("Set MONGODB_URI in your secure environment before running this migration.")

    content = load_portal_content()
    credentials = {
        "cloud_name": os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip(),
        "api_key": os.environ.get("CLOUDINARY_API_KEY", "").strip(),
        "api_secret": os.environ.get("CLOUDINARY_API_SECRET", "").strip(),
    }
    database_name = os.environ.get("MONGODB_DATABASE", "ppru").strip() or "ppru"
    collection_name = os.environ.get("MONGODB_COLLECTION", "portal_data").strip() or "portal_data"
    namespace = os.environ.get("MONGODB_NAMESPACE", "ppru").strip() or "ppru"
    document_id = f"{namespace}:{args.environment}"
    store = MongoPortalStore(
        preferences_file=BASE_DIR / "preferensi.json",
        news_file=BASE_DIR / "berita.json",
        gallery_file=BASE_DIR / "gallery.json",
        seed_preferences_file=BASE_DIR / "data" / "site.json",
        seed_news_file=BASE_DIR / "data" / "berita.json",
        seed_gallery_file=BASE_DIR / "data" / "gallery.json",
        mongo_uri=mongo_uri,
        database_name=database_name,
        collection_name=collection_name,
        document_id=document_id,
    )

    try:
        collection = store._get_collection()
        existing = collection.find_one({"_id": document_id})
        if existing is not None and not args.replace_existing:
            raise SystemExit(
                f"MongoDB document {document_id} already exists; not overwriting it. "
                "Use --replace-existing only after reviewing the existing Atlas data."
            )
        try:
            migrated, counts = prepare_portal_content(content, cloudinary_credentials=credentials)
        except Exception as error:
            raise SystemExit(
                f"Could not prepare portal data ({type(error).__name__}). Check JSON and Cloudinary configuration."
            ) from None
        store.save(migrated)
    except PersistentStorageError:
        raise SystemExit(
            "MongoDB Atlas is unavailable. Check MONGODB_URI and Atlas Network Access; "
            "the save result is unconfirmed, so inspect the target document before retrying."
        ) from None
    except Exception as error:
        raise SystemExit(f"MongoDB migration failed ({type(error).__name__}); no successful save was confirmed.") from None
    finally:
        if store.client is not None:
            store.client.close()

    print(
        f"Migrated {counts['news_items']} news item(s), {counts['gallery_items']} gallery item(s), "
        f"and portal preferences to MongoDB document {document_id}. "
        f"{counts['local_image_urls']} local image reference(s) use {counts['cloudinary_assets']} "
        "Cloudinary optimized preview asset(s). Local JSON files were not modified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
