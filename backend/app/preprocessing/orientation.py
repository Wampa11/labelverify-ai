"""
EXIF orientation correction for uploaded label photos.

Architectural responsibility: rotate/flip pixels to match intended viewing orientation
without otherwise altering image content.
"""

from __future__ import annotations

from PIL import Image, ImageOps


def apply_exif_orientation(image: Image.Image) -> tuple[Image.Image, bool]:
    """
    Return an image with EXIF orientation applied, and whether a transform occurred.

    Uses Pillow's ImageOps.exif_transpose. The returned image may be the same object
    if no orientation tag required a change.
    """
    before_size = image.size
    before_mode = image.mode
    transposed = ImageOps.exif_transpose(image)
    if transposed is None:
        return image, False
    changed = transposed.size != before_size or transposed.mode != before_mode
    # exif_transpose may return a copy even when orientation is 1; compare orientation tag.
    if not changed:
        orientation = _read_orientation(image)
        changed = orientation not in (None, 1)
    return transposed, changed


def _read_orientation(image: Image.Image) -> int | None:
    """Read EXIF orientation tag when present."""
    try:
        exif = image.getexif()
    except Exception:  # noqa: BLE001 — EXIF parse failures mean "no usable orientation"
        return None
    if not exif:
        return None
    # 274 is the EXIF Orientation tag.
    value = exif.get(274)
    return int(value) if value is not None else None
