"""
Upload validation and sanitisation (docs/MEDIA.md Part 1b).

The server never trusts what the client claims about an upload:

* **Type** is decided by sniffing magic bytes, not the `Content-Type` header or
  the file extension — so `payload.exe` renamed to `photo.jpg` is still
  rejected.
* **Size** is enforced against `settings.MEDIA_UPLOAD_MAX_BYTES`.
* **Images are re-encoded** through Pillow, which drops EXIF and any trailing
  payload smuggled into a polyglot file.
* **Filenames** are sanitised for display only; the storage key is generated
  (see models), so a crafted name can never influence the storage path.
"""
from __future__ import annotations

import io
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image

# Magic-byte signatures for the allowed types. Anything not matched here is
# refused, so the allow-list is positive rather than a blocklist.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),
)

# Which Pillow format to re-encode each image type through.
_IMAGE_FORMATS: dict[str, str] = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/gif": "GIF",
}

_KINDS: dict[str, str] = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "application/pdf": "document",
    # Office documents (docx/xlsx/pptx) are zip containers.
    "application/zip": "document",
}

_EXTENSIONS: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
}

MAX_NAME_LENGTH = 255


def detect_content_type(data: bytes) -> str | None:
    """Return the MIME type implied by the leading magic bytes, or None.

    None means "not an allowed type" — including executables (e.g. a Windows
    `MZ` header), which match no signature.
    """
    for signature, mime in _SIGNATURES:
        if data.startswith(signature):
            return mime
    return None


def kind_for(mime: str) -> str:
    return _KINDS.get(mime, "other")


def extension_for(mime: str) -> str:
    return _EXTENSIONS.get(mime, "")


def image_format_for(mime: str) -> str | None:
    return _IMAGE_FORMATS.get(mime)


def safe_original_name(name: str) -> str:
    """Sanitise a client-supplied filename for *display* purposes.

    Strips any directory component (so "/etc/passwd" cannot masquerade as a
    path), removes NUL bytes, and truncates. The result is never used to build
    the storage key.
    """
    if not name:
        return "upload"
    name = name.replace("\x00", "")
    # Handle both POSIX and Windows separators regardless of host platform.
    name = name.replace("\\", "/").split("/")[-1]
    name = os.path.basename(name).strip()
    if not name:
        return "upload"
    return name[:MAX_NAME_LENGTH]


def _read_all(f) -> bytes:
    try:
        f.seek(0)
    except (AttributeError, OSError):
        pass
    data = f.read()
    try:
        f.seek(0)
    except (AttributeError, OSError):
        pass
    return data


def validate_upload(f) -> tuple[str, str, int]:
    """Validate an uploaded file object.

    Returns ``(mime, kind, size_bytes)``. Raises ``ValidationError`` when the
    file is larger than ``MEDIA_UPLOAD_MAX_BYTES`` or its magic bytes do not
    match an allowed type.
    """
    data = _read_all(f)
    size = len(data)

    max_bytes = getattr(settings, "MEDIA_UPLOAD_MAX_BYTES", 20 * 1024 * 1024)
    if size > max_bytes:
        raise ValidationError(
            f"File is too large ({size} bytes); the limit is {max_bytes} bytes."
        )

    mime = detect_content_type(data)
    if mime is None:
        raise ValidationError(
            "File type is not allowed. Permitted types: JPEG, PNG, GIF, PDF, ZIP."
        )

    return mime, kind_for(mime), size


def sanitise_image(f, image_format: str) -> io.BytesIO:
    """Re-encode an image through Pillow, dropping EXIF and trailing payloads.

    Only pixel data survives the round trip, so an APP1/EXIF segment (or bytes
    appended after the image) cannot reach storage.
    """
    data = _read_all(f)
    with Image.open(io.BytesIO(data)) as img:
        if image_format == "JPEG" and img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        # Paste the pixels into a fresh image so no metadata rides along
        # (a fresh Image has empty .info, and paste copies pixels only).
        clean = Image.new(img.mode, img.size)
        clean.paste(img)
        out = io.BytesIO()
        # No exif= argument and no pnginfo= argument: metadata is dropped.
        clean.save(out, format=image_format)
    out.seek(0)
    return out
