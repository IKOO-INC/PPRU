"""Cloudinary upload and optimized-delivery helpers for portal images."""
from pathlib import Path

import cloudinary
from cloudinary import uploader, utils
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024
UPLOAD_TRANSFORMATION = {
    "width": 2400,
    "height": 2400,
    "crop": "limit",
    "quality": "auto:good",
}
DELIVERY_TRANSFORMATION = {
    "width": 1600,
    "height": 1600,
    "crop": "limit",
    "quality": "auto:good",
    "fetch_format": "auto",
}
FOLDER_NAMES = {"site", "news", "gallery"}


class CloudinaryConfigurationError(RuntimeError):
    """Raised when required Cloudinary credentials are missing."""


class InvalidImageUpload(ValueError):
    """Raised when an upload is not one of the supported raster image types."""


def _credentials_values(credentials: dict) -> tuple[str, str, str]:
    cloud_name = str(credentials.get("cloud_name", "")).strip()
    api_key = str(credentials.get("api_key", "")).strip()
    api_secret = str(credentials.get("api_secret", "")).strip()
    if not (cloud_name and api_key and api_secret):
        raise CloudinaryConfigurationError(
            "Cloudinary belum dikonfigurasi. Isi CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, dan CLOUDINARY_API_SECRET."
        )
    cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)
    return cloud_name, api_key, api_secret


def _validate_image_file(file_storage) -> str:
    if not file_storage or not file_storage.filename:
        raise InvalidImageUpload("Pilih file gambar yang akan diunggah.")
    extension = Path(secure_filename(file_storage.filename)).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise InvalidImageUpload("Format gambar harus JPG, PNG, GIF, atau WebP.")

    file_storage.stream.seek(0, 2)
    file_size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if file_size > MAX_IMAGE_SIZE:
        raise InvalidImageUpload("Ukuran file gambar maksimal 10 MB.")

    header = file_storage.stream.read(12)
    file_storage.stream.seek(0)
    signatures = {
        ".jpg": lambda value: value.startswith(b"\xff\xd8\xff"),
        ".jpeg": lambda value: value.startswith(b"\xff\xd8\xff"),
        ".png": lambda value: value.startswith(b"\x89PNG\r\n\x1a\n"),
        ".gif": lambda value: value.startswith((b"GIF87a", b"GIF89a")),
        ".webp": lambda value: len(value) >= 12 and value[:4] == b"RIFF" and value[8:12] == b"WEBP",
    }
    if not signatures[extension](header):
        raise InvalidImageUpload("Isi file tidak cocok dengan format gambar yang dipilih.")
    return extension


def _optimized_result(result: dict, cloud_name: str) -> dict:
    public_id = result.get("public_id")
    if not public_id:
        raise RuntimeError("Cloudinary tidak mengembalikan public_id untuk gambar.")
    delivery_url, _ = utils.cloudinary_url(
        public_id,
        cloud_name=cloud_name,
        resource_type="image",
        secure=True,
        version=result.get("version"),
        transformation=DELIVERY_TRANSFORMATION,
    )
    if not delivery_url.startswith("https://res.cloudinary.com/"):
        raise RuntimeError("Cloudinary tidak mengembalikan URL gambar HTTPS yang valid.")
    return {
        "url": delivery_url,
        "public_id": public_id,
        "secure_url": result.get("secure_url", delivery_url),
        "format": result.get("format"),
        "bytes": result.get("bytes"),
    }


def upload_image(file_storage, credentials: dict, folder: str) -> dict:
    """Upload a validated raster image and return a compressed Cloudinary URL."""
    _validate_image_file(file_storage)
    if folder not in FOLDER_NAMES:
        raise ValueError("Folder Cloudinary tidak dikenal.")
    cloud_name, _, _ = _credentials_values(credentials)
    result = uploader.upload(
        file_storage.stream,
        resource_type="image",
        folder=f"ppru/{folder}",
        allowed_formats=["jpg", "jpeg", "png", "gif", "webp"],
        transformation=UPLOAD_TRANSFORMATION,
        use_filename=False,
        unique_filename=True,
        overwrite=False,
    )
    return _optimized_result(result, cloud_name)


def upload_local_image(
    file_path: str | Path,
    credentials: dict,
    folder: str = "site",
    public_id: str | None = None,
) -> dict:
    """Upload a trusted local image, optionally using a stable ID for repeatable migration."""
    path = Path(file_path)
    extension = path.suffix.lower()
    if not path.is_file() or (extension not in ALLOWED_IMAGE_EXTENSIONS and extension != ".svg"):
        raise InvalidImageUpload(f"File lokal bukan format gambar yang didukung: {path.name}")
    if folder not in FOLDER_NAMES:
        raise ValueError("Folder Cloudinary tidak dikenal.")

    stable_options = {}
    if public_id:
        stable_options = {
            "public_id": public_id,
            "unique_filename": False,
            "overwrite": True,
        }

    if extension == ".svg":
        cloud_name, _, _ = _credentials_values(credentials)
        result = uploader.upload(
            str(path),
            resource_type="image",
            folder=f"ppru/{folder}",
            allowed_formats=["svg"],
            use_filename=False,
            unique_filename=not bool(public_id),
            overwrite=bool(public_id),
            **({"public_id": public_id} if public_id else {}),
        )
    else:
        with path.open("rb") as stream:
            file_storage = FileStorage(stream=stream, filename=path.name)
            if not public_id:
                return upload_image(file_storage, credentials, folder)
            _validate_image_file(file_storage)
            cloud_name, _, _ = _credentials_values(credentials)
            result = uploader.upload(
                file_storage.stream,
                resource_type="image",
                folder=f"ppru/{folder}",
                allowed_formats=["jpg", "jpeg", "png", "gif", "webp"],
                transformation=UPLOAD_TRANSFORMATION,
                use_filename=False,
                **stable_options,
            )
    return _optimized_result(result, cloud_name)
