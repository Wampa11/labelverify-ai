"""
Programmatic image fixtures for preprocessing and validation tests.

Architectural responsibility: generate deterministic JPEG/PNG/WebP bytes without fake labels.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def make_rgb_image(
    width: int = 640,
    height: int = 480,
    *,
    color: tuple[int, int, int] = (220, 220, 220),
    with_text_bars: bool = True,
) -> Image.Image:
    """Create a simple synthetic label-like RGB image with high-contrast bars."""
    image = Image.new("RGB", (width, height), color)
    if with_text_bars:
        draw = ImageDraw.Draw(image)
        for index in range(8):
            y = 40 + index * 40
            draw.rectangle((40, y, width - 40, y + 18), fill=(20, 20, 20))
        draw.rectangle((40, height - 80, width - 40, height - 40), fill=(30, 30, 140))
    return image


def encode_image(image: Image.Image, fmt: str, **save_kwargs: object) -> bytes:
    """Encode a Pillow image to bytes in the given format (JPEG/PNG/WEBP)."""
    buffer = io.BytesIO()
    to_save = image
    if fmt.upper() in {"JPEG", "JPG"} and image.mode != "RGB":
        to_save = image.convert("RGB")
    to_save.save(buffer, format=fmt.upper() if fmt.upper() != "JPG" else "JPEG", **save_kwargs)
    return buffer.getvalue()


def jpeg_bytes(**kwargs: object) -> bytes:
    """Valid JPEG fixture bytes."""
    return encode_image(make_rgb_image(**kwargs), "JPEG", quality=90)  # type: ignore[arg-type]


def png_bytes(**kwargs: object) -> bytes:
    """Valid PNG fixture bytes."""
    return encode_image(make_rgb_image(**kwargs), "PNG")  # type: ignore[arg-type]


def webp_bytes(**kwargs: object) -> bytes:
    """Valid WebP fixture bytes."""
    return encode_image(make_rgb_image(**kwargs), "WEBP", quality=90)  # type: ignore[arg-type]


def jpeg_with_exif_orientation(orientation: int = 6) -> bytes:
    """
    JPEG with EXIF Orientation tag set (6 ≈ 90° CW).

    Used to verify orientation correction changes pixel layout.
    """
    image = make_rgb_image(400, 200, color=(200, 200, 200))
    # Distinctive asymmetric mark near top-left before orientation.
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 60, 60), fill=(255, 0, 0))

    exif = image.getexif()
    exif[274] = orientation
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90, exif=exif.tobytes())
    return buffer.getvalue()


def blurred_jpeg_bytes() -> bytes:
    """Heavily blurred JPEG expected to score poor/warning on blur metric."""
    image = make_rgb_image(640, 480)
    image = image.filter(ImageFilter.GaussianBlur(radius=12))
    return encode_image(image, "JPEG", quality=90)


def dark_jpeg_bytes() -> bytes:
    """Very dark image for brightness POOR/WARNING checks."""
    return encode_image(make_rgb_image(640, 480, color=(8, 8, 8), with_text_bars=False), "JPEG")


def low_contrast_jpeg_bytes() -> bytes:
    """Low-contrast gray image for contrast warnings."""
    arr = np.full((480, 640, 3), 128, dtype=np.uint8)
    arr[100:120, 50:600] = 140
    image = Image.fromarray(arr, mode="RGB")
    return encode_image(image, "JPEG", quality=90)


def overexposed_jpeg_bytes() -> bytes:
    """Near-white image with clipping for overexposure checks."""
    return encode_image(
        make_rgb_image(640, 480, color=(252, 252, 252), with_text_bars=False),
        "JPEG",
        quality=90,
    )


def corrupt_jpeg_bytes() -> bytes:
    """JPEG magic header followed by invalid payload."""
    return b"\xff\xd8\xff\xe0" + b"not-a-real-jpeg-payload" * 20


def tiny_jpeg_bytes() -> bytes:
    """Valid but undersized JPEG for dimension rejection."""
    return encode_image(make_rgb_image(50, 50, with_text_bars=False), "JPEG")
