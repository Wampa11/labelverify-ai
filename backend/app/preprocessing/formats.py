"""
Image format detection via magic bytes and Pillow.

Architectural responsibility: identify true image content type without trusting
client MIME or extension.
PDF is recognized for clear rejection and future extension — not processed in Phase 2.
"""

from __future__ import annotations

from enum import StrEnum

from app.models.image_analysis import ImageFormat


class DetectedContentKind(StrEnum):
    """Coarse content classification for upload sniffing."""

    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"
    PDF = "pdf"
    UNKNOWN = "unknown"


_FORMAT_BY_KIND: dict[DetectedContentKind, ImageFormat] = {
    DetectedContentKind.JPEG: ImageFormat.JPEG,
    DetectedContentKind.PNG: ImageFormat.PNG,
    DetectedContentKind.WEBP: ImageFormat.WEBP,
}


def sniff_content_kind(data: bytes) -> DetectedContentKind:
    """
    Detect content kind from leading bytes.

    Does not decode the full image; used as a first gate before Pillow open.
    """
    if len(data) < 12:
        return DetectedContentKind.UNKNOWN
    if data.startswith(b"\xff\xd8\xff"):
        return DetectedContentKind.JPEG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return DetectedContentKind.PNG
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return DetectedContentKind.WEBP
    if data.startswith(b"%PDF"):
        return DetectedContentKind.PDF
    return DetectedContentKind.UNKNOWN


def to_supported_image_format(kind: DetectedContentKind) -> ImageFormat | None:
    """Map a sniffed kind to an accepted ImageFormat, or None if unsupported."""
    return _FORMAT_BY_KIND.get(kind)


def pillow_format_to_image_format(pillow_format: str | None) -> ImageFormat | None:
    """Map Pillow's format string to ImageFormat."""
    if pillow_format is None:
        return None
    normalized = pillow_format.upper()
    if normalized in {"JPEG", "JPG"}:
        return ImageFormat.JPEG
    if normalized == "PNG":
        return ImageFormat.PNG
    if normalized == "WEBP":
        return ImageFormat.WEBP
    return None
