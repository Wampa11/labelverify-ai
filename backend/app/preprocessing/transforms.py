"""
Conservative pixel transforms for display and OCR-prepared images.

Architectural responsibility: modular, independently testable image operations.
Each function documents whether it mutates or returns a new image (always new here).
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image


def to_rgb(image: Image.Image) -> Image.Image:
    """
    Convert to RGB for a predictable color space.

    Returns a new image. Alpha is composited onto white when present.
    """
    if image.mode == "RGB":
        return image.copy()
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image.convert("RGB")


def resize_max_edge(image: Image.Image, max_edge_px: int) -> tuple[Image.Image, bool]:
    """
    Downscale so the longest edge is at most max_edge_px (LANCZOS).

    Returns (image, resized_flag). Never upscales. Returns a new image when resized.
    """
    width, height = image.size
    longest = max(width, height)
    if longest <= max_edge_px:
        return image.copy(), False
    scale = max_edge_px / float(longest)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS), True


def to_grayscale_array(image: Image.Image) -> np.ndarray:
    """Convert a Pillow image to an 8-bit grayscale NumPy array (new array)."""
    gray = image.convert("L")
    return np.asarray(gray, dtype=np.uint8)


def apply_clahe(gray: np.ndarray, clip_limit: float = 2.0, tile_grid: int = 8) -> np.ndarray:
    """
    Contrast-limited adaptive histogram equalization for OCR readiness.

    Conservative defaults avoid extreme local contrast that can invent edges.
    Returns a new array.
    """
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_grid, tile_grid))
    return clahe.apply(gray)


def mild_denoise(gray: np.ndarray) -> np.ndarray:
    """
    Light non-local means denoising to reduce sensor noise before OCR.

    Uses a small filter strength so fine text strokes are less likely to be erased.
    Returns a new array.
    """
    return cv2.fastNlMeansDenoising(gray, None, h=6, templateWindowSize=7, searchWindowSize=21)


def mild_unsharp(gray: np.ndarray, amount: float = 0.4, radius: float = 1.0) -> np.ndarray:
    """
    Mild unsharp mask to restore edge clarity after resize/denoise.

    Intentionally weak; aggressive sharpening can create OCR artifacts.
    Returns a new array.
    """
    blurred = cv2.GaussianBlur(gray, (0, 0), radius)
    sharpened = cv2.addWeighted(gray, 1.0 + amount, blurred, -amount, 0)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def encode_jpeg_base64(image: Image.Image, *, quality: int = 92) -> tuple[str, str]:
    """Encode an RGB image as JPEG base64. Returns (base64_str, media_type)."""
    import base64
    import io

    buffer = io.BytesIO()
    rgb = to_rgb(image)
    rgb.save(buffer, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii"), "image/jpeg"


def encode_png_gray_base64(gray: np.ndarray) -> tuple[str, str]:
    """Encode a grayscale array as PNG base64. Returns (base64_str, media_type)."""
    import base64
    import io

    image = Image.fromarray(gray, mode="L")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii"), "image/png"
