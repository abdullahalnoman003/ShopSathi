"""Local media storage for uploaded images. Files are served by the backend at /media/<key>."""

import shutil
import uuid
from pathlib import Path

from app.core.config import get_settings

# Image type is detected from the file's first bytes, never trusted from the client's filename/header.
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
]


class InvalidImage(ValueError):
    pass


def detect_image_extension(data: bytes) -> str:
    for sig, ext in _SIGNATURES:
        if data.startswith(sig):
            return ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    raise InvalidImage("Only JPEG, PNG or WebP images are allowed")


class StorageService:
    def __init__(self) -> None:
        s = get_settings()
        self.root = Path(s.media_root).resolve()
        self.public_base = s.backend_public_url.rstrip("/")
        self.max_bytes = s.max_upload_mb * 1024 * 1024

    def validate(self, data: bytes) -> str:
        """Return the file extension, or raise InvalidImage."""
        if not data:
            raise InvalidImage("The file is empty")
        if len(data) > self.max_bytes:
            raise InvalidImage(f"Image is larger than {get_settings().max_upload_mb} MB")
        return detect_image_extension(data)

    def save(self, shop_id: int, data: bytes, ext: str) -> str:
        """Store the bytes and return the storage key (what the database keeps)."""
        key = f"shops/{shop_id}/products/{uuid.uuid4().hex}.{ext}"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    @staticmethod
    def is_external(key: str) -> bool:
        """Imported products may point at photos hosted elsewhere (full http(s) URLs)."""
        return key.startswith(("http://", "https://"))

    def delete(self, key: str) -> None:
        if self.is_external(key):
            return  # not our file
        path = (self.root / key).resolve()
        if self.root in path.parents:  # never touch anything outside the media folder
            path.unlink(missing_ok=True)

    def delete_shop_files(self, shop_id: int) -> int:
        """Remove every file this shop uploaded (the whole shops/<id>/ folder). Returns the number of files."""
        folder = (self.root / "shops" / str(int(shop_id))).resolve()
        if not folder.is_dir() or (self.root / "shops").resolve() not in folder.parents:
            return 0
        count = sum(1 for p in folder.rglob("*") if p.is_file())
        shutil.rmtree(folder)
        return count

    def url(self, key: str) -> str:
        if self.is_external(key):
            return key
        return f"{self.public_base}/media/{key}"
