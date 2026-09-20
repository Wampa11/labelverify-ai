"""
OCR-oriented preprocessing profiles for evaluation and future pipeline wiring.

Architectural responsibility: produce FAST vs ENHANCED OCR inputs with configurable
max edge — without mutating the original upload or display representation.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from PIL import Image

from app.models.image_analysis import PreprocessingOperation
from app.preprocessing.geometry import maybe_deskew, plan_perspective_correction
from app.preprocessing.orientation import apply_exif_orientation
from app.preprocessing.transforms import (
    apply_clahe,
    mild_denoise,
    mild_unsharp,
    resize_max_edge,
    to_grayscale_array,
    to_rgb,
)


class OcrPreprocessProfile(StrEnum):
    """Named preprocessing strategies compared in Phase 3 evaluation."""

    FAST = "fast"
    ENHANCED = "enhanced"


@dataclass(frozen=True)
class OcrPreparedImage:
    """Bytes + metadata for an OCR-ready grayscale (or RGB) working image."""

    image_bytes: bytes
    media_type: str
    width_px: int
    height_px: int
    profile: OcrPreprocessProfile
    max_edge_px: int
    operations: list[PreprocessingOperation]
    gray: np.ndarray


def prepare_for_ocr(
    image: Image.Image,
    *,
    profile: OcrPreprocessProfile,
    max_edge_px: int,
) -> OcrPreparedImage:
    """
    Build an OCR working image from a decoded Pillow image.

    FAST: orientation → RGB → resize → grayscale (no CLAHE/denoise/deskew/unsharp).
    ENHANCED: orientation → RGB → resize → grayscale → CLAHE → denoise →
    optional deskew → mild unsharp (Phase 2 OCR path).
    """
    operations: list[PreprocessingOperation] = []

    oriented, orientation_changed = apply_exif_orientation(image)
    operations.append(
        PreprocessingOperation(
            name="exif_orientation",
            applied=orientation_changed,
            detail=(
                "Applied EXIF orientation tag"
                if orientation_changed
                else "No orientation correction needed"
            ),
        ),
    )

    rgb = to_rgb(oriented)
    operations.append(
        PreprocessingOperation(
            name="convert_rgb",
            applied=True,
            detail="Converted to RGB",
        ),
    )

    resized, did_resize = resize_max_edge(rgb, max_edge_px)
    operations.append(
        PreprocessingOperation(
            name="ocr_max_edge_resize",
            applied=did_resize,
            detail=f"Longest edge limited to {max_edge_px}px"
            if did_resize
            else f"Within {max_edge_px}px; no resize",
        ),
    )

    gray = to_grayscale_array(resized)
    operations.append(
        PreprocessingOperation(
            name="grayscale",
            applied=True,
            detail="Converted to 8-bit grayscale",
        ),
    )

    if profile == OcrPreprocessProfile.ENHANCED:
        gray = apply_clahe(gray)
        operations.append(
            PreprocessingOperation(
                name="clahe_contrast",
                applied=True,
                detail="CLAHE clipLimit=2.0",
            ),
        )
        gray = mild_denoise(gray)
        operations.append(
            PreprocessingOperation(
                name="mild_denoise",
                applied=True,
                detail="Non-local means denoise h=6",
            ),
        )
        perspective = plan_perspective_correction()
        operations.append(
            PreprocessingOperation(
                name="perspective_correction",
                applied=False,
                detail=perspective.reason,
            ),
        )
        deskew = maybe_deskew(gray)
        if deskew.applied and deskew.corrected_gray is not None:
            gray = deskew.corrected_gray
            operations.append(
                PreprocessingOperation(
                    name="deskew",
                    applied=True,
                    detail=f"Rotated by {deskew.angle_degrees:.2f} degrees",
                ),
            )
        else:
            operations.append(
                PreprocessingOperation(
                    name="deskew",
                    applied=False,
                    detail=deskew.skipped_reason or "deskew_not_applied",
                ),
            )
        gray = mild_unsharp(gray)
        operations.append(
            PreprocessingOperation(
                name="mild_unsharp",
                applied=True,
                detail="Mild unsharp amount=0.4",
            ),
        )
    else:
        operations.append(
            PreprocessingOperation(
                name="enhanced_skipped",
                applied=False,
                detail="FAST profile: skipped CLAHE, denoise, deskew, unsharp",
            ),
        )

    png_bytes = _encode_gray_png(gray)
    height, width = gray.shape[:2]
    return OcrPreparedImage(
        image_bytes=png_bytes,
        media_type="image/png",
        width_px=int(width),
        height_px=int(height),
        profile=profile,
        max_edge_px=max_edge_px,
        operations=operations,
        gray=gray,
    )


def prepare_for_ocr_from_bytes(
    data: bytes,
    *,
    profile: OcrPreprocessProfile,
    max_edge_px: int,
) -> OcrPreparedImage:
    """Decode bytes then prepare for OCR."""
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        return prepare_for_ocr(image, profile=profile, max_edge_px=max_edge_px)


def _encode_gray_png(gray: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(gray, mode="L").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
