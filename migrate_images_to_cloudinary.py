"""One-time migration of existing /static image references to Cloudinary.

Configure CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET
in the process environment, then run: python migrate_images_to_cloudinary.py
"""
import os
from pathlib import Path, PurePosixPath

from cloudinary_service import upload_local_image
from content_store import JsonContentStore, JsonListStore, JsonPortalStore


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = (BASE_DIR / "static").resolve()
SEED_DIR = BASE_DIR / "data"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}


def _collect_local_image_urls(value, found=None):
    found = found if found is not None else set()
    if isinstance(value, dict):
        for item in value.values():
            _collect_local_image_urls(item, found)
    elif isinstance(value, list):
        for item in value:
            _collect_local_image_urls(item, found)
    elif isinstance(value, str) and value.startswith("/static/"):
        suffix = PurePosixPath(value.split("?", 1)[0]).suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            found.add(value.split("?", 1)[0])
    return found


def _local_path_from_url(image_url: str) -> Path:
    relative = PurePosixPath(image_url).relative_to("/static")
    if ".." in relative.parts:
        raise ValueError(f"Unsafe static image path: {image_url}")
    local_path = (STATIC_DIR / Path(*relative.parts)).resolve()
    if STATIC_DIR not in local_path.parents or not local_path.is_file():
        raise FileNotFoundError(f"Local image does not exist or is outside static/: {image_url}")
    return local_path


def _replace_urls(value, url_map):
    if isinstance(value, dict):
        return {key: _replace_urls(item, url_map) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_urls(item, url_map) for item in value]
    if isinstance(value, str):
        bare_url = value.split("?", 1)[0]
        if bare_url in url_map:
            return url_map[bare_url]
    return value


def _load_seed_content():
    preferences = JsonContentStore(SEED_DIR / "site.json").load()
    news = JsonListStore(SEED_DIR / "berita.json").load()
    gallery = JsonListStore(SEED_DIR / "gallery.json").load()
    return {**preferences, "news": news, "gallery": gallery}


def main():
    credentials = {
        "cloud_name": os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip(),
        "api_key": os.environ.get("CLOUDINARY_API_KEY", "").strip(),
        "api_secret": os.environ.get("CLOUDINARY_API_SECRET", "").strip(),
    }
    if not all(credentials.values()):
        raise SystemExit(
            "Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET before running this migration."
        )

    store = JsonPortalStore(
        preferences_file=BASE_DIR / "preferensi.json",
        news_file=BASE_DIR / "berita.json",
        gallery_file=BASE_DIR / "gallery.json",
        seed_preferences_file=SEED_DIR / "site.json",
        seed_news_file=SEED_DIR / "berita.json",
        seed_gallery_file=SEED_DIR / "gallery.json",
    )
    current_content = store.load()
    seed_content = _load_seed_content()
    image_urls = sorted(_collect_local_image_urls(current_content) | _collect_local_image_urls(seed_content))
    if not image_urls:
        print("No local image URLs need migration.")
        return

    url_map = {}
    for image_url in image_urls:
        local_path = _local_path_from_url(image_url)
        uploaded = upload_local_image(local_path, credentials, folder="site")
        url_map[image_url] = uploaded["url"]
        print(f"Migrated {image_url} -> {uploaded['url']}")

    store.save(_replace_urls(current_content, url_map))
    seed_content = _replace_urls(seed_content, url_map)
    JsonContentStore(SEED_DIR / "site.json").save(
        {key: value for key, value in seed_content.items() if key not in {"news", "gallery"}}
    )
    JsonListStore(SEED_DIR / "berita.json").save(seed_content["news"])
    JsonListStore(SEED_DIR / "gallery.json").save(seed_content["gallery"])
    print(f"Updated {len(url_map)} unique local image URL(s) in runtime and seed JSON files.")


if __name__ == "__main__":
    main()
