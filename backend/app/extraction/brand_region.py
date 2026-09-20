"""
Generic brand-region cropping for selective OCR escalation.

Architectural responsibility: derive candidate brand crops from label geometry
and OCR layout evidence without fixture-specific coordinates.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from app.ocr.base import OcrResult, OcrWord


@dataclass(frozen=True)
class BrandRegionCrop:
    """One candidate brand region cropped from the OCR-prepared image."""

    image_bytes: bytes
    method: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    source_word_count: int


def crop_upper_region(
    image_bytes: bytes,
    *,
    top_fraction: float = 0.45,
) -> BrandRegionCrop:
    """Crop the upper portion of the label (general heuristic)."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.load()
        width, height = image.size
        y_max = max(1, int(height * top_fraction))
        crop = image.crop((0, 0, width, y_max))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        return BrandRegionCrop(
            image_bytes=buf.getvalue(),
            method="upper_fraction",
            x_min=0.0,
            y_min=0.0,
            x_max=float(width),
            y_max=float(y_max),
            source_word_count=0,
        )


def crop_prominent_band(
    image_bytes: bytes,
    ocr: OcrResult,
    *,
    upper_fraction: float = 0.55,
    top_n: int = 4,
    pad_px: float = 12.0,
) -> BrandRegionCrop | None:
    """
    Crop a band around the tallest OCR words in the upper half.

    Uses first-pass boxes only — no fixture-specific coordinates.
    """
    if not ocr.words or not ocr.image_height_px:
        return None
    height = float(ocr.image_height_px)
    width = float(ocr.image_width_px or 1)
    candidates: list[tuple[float, float, float, float, float, str]] = []
    for word in ocr.words:
        box = word.bounding_box
        if not box:
            continue
        y_min = float(box["y_min"])
        y_max = float(box["y_max"])
        x_min = float(box["x_min"])
        x_max = float(box["x_max"])
        if y_min > height * upper_fraction:
            continue
        h = max(1.0, y_max - y_min)
        candidates.append((h, x_min, y_min, x_max, y_max, word.text))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    top = candidates[: min(top_n, len(candidates))]
    x0 = max(0.0, min(t[1] for t in top) - pad_px)
    y0 = max(0.0, min(t[2] for t in top) - pad_px)
    x1 = min(width, max(t[3] for t in top) + pad_px)
    y1 = min(height, max(t[4] for t in top) + pad_px)
    if x1 - x0 < 20 or y1 - y0 < 12:
        return None
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.load()
        # OCR boxes are in prepared-image coordinates; crop that same image.
        crop = image.crop((int(x0), int(y0), int(x1), int(y1)))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        return BrandRegionCrop(
            image_bytes=buf.getvalue(),
            method="prominent_upper_words",
            x_min=x0,
            y_min=y0,
            x_max=x1,
            y_max=y1,
            source_word_count=len(top),
        )


def select_brand_region(
    prepared_image_bytes: bytes,
    ocr: OcrResult,
    *,
    prefer_upper: bool = False,
) -> BrandRegionCrop:
    """
    Prefer the Phase 8.8 best region (prominent upper band); fall back to upper crop.

    When whole-label brand boxes are unreliable (UNCERTAIN/NOT_FOUND), prefer the
    generic upper fraction so escalation is not anchored on garbage OCR boxes.
    """
    if prefer_upper:
        return crop_upper_region(prepared_image_bytes, top_fraction=0.55)
    band = crop_prominent_band(prepared_image_bytes, ocr)
    if band is not None:
        return band
    return crop_upper_region(prepared_image_bytes, top_fraction=0.45)


def words_avg_height(words: list[OcrWord]) -> float:
    """Mean bounding-box height for prominence checks."""
    if not words:
        return 0.0
    heights = []
    for word in words:
        box = word.bounding_box or {}
        heights.append(max(0.0, float(box.get("y_max", 0) - box.get("y_min", 0))))
    return sum(heights) / len(heights) if heights else 0.0
