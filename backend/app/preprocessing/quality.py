"""
Lightweight, explainable image-quality assessment for OCR readiness awareness.

Architectural responsibility: measure resolution, blur, brightness, contrast, and clipping.
Statuses are engineering heuristics — not regulatory findings and not AI confidence.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import cv2
import numpy as np

from app.models.image_analysis import (
    ImageQualityAssessment,
    QualityMeasurements,
    QualityStatus,
)

# --- Thresholds (prototype heuristics; see docs and ADR) ---
#
# SHORT_SIDE: label photos under ~400px often lose fine text for OCR demos.
SHORT_SIDE_WARNING_PX = 400
SHORT_SIDE_POOR_PX = 200
#
# Laplacian variance: common OpenCV blur heuristic; absolute values depend on
# resolution and content. Tuned on synthetic fixtures for this prototype.
LAPLACIAN_WARNING = 100.0
LAPLACIAN_POOR = 40.0
#
# Brightness / contrast on 8-bit grayscale.
BRIGHTNESS_DARK_WARNING = 45.0
BRIGHTNESS_DARK_POOR = 25.0
BRIGHTNESS_BRIGHT_WARNING = 210.0
BRIGHTNESS_BRIGHT_POOR = 235.0
CONTRAST_WARNING = 28.0
CONTRAST_POOR = 15.0
#
# Clipping: fraction of pixels near black/white.
CLIP_LOW = 5
CLIP_HIGH = 250
CLIP_WARNING_FRACTION = 0.05
CLIP_POOR_FRACTION = 0.15


@dataclass(frozen=True)
class _Indicator:
    status: QualityStatus
    warning: str | None


def assess_image_quality(
    gray: np.ndarray,
    *,
    width_px: int,
    height_px: int,
) -> ImageQualityAssessment:
    """
    Evaluate quality indicators on an 8-bit grayscale array.

    Uses the display/orientation-corrected geometry for dimension reporting;
    blur/brightness metrics use the provided grayscale (typically pre-OCR).
    """
    shortest = min(width_px, height_px)
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    mean_brightness = float(np.mean(gray))
    contrast_std = float(np.std(gray))
    near_black = float(np.mean(gray <= CLIP_LOW))
    near_white = float(np.mean(gray >= CLIP_HIGH))

    indicators = [
        _assess_resolution(shortest),
        _assess_blur(laplacian_var),
        _assess_brightness(mean_brightness),
        _assess_contrast(contrast_std),
        _assess_clipping(near_black, near_white),
    ]

    warnings = [item.warning for item in indicators if item.warning]
    status = _worst_status(item.status for item in indicators)

    measurements = QualityMeasurements(
        width_px=width_px,
        height_px=height_px,
        shortest_side_px=shortest,
        laplacian_variance=round(laplacian_var, 3),
        mean_brightness=round(mean_brightness, 3),
        contrast_std=round(contrast_std, 3),
        near_black_fraction=round(near_black, 4),
        near_white_fraction=round(near_white, 4),
    )
    return ImageQualityAssessment(status=status, measurements=measurements, warnings=warnings)


def _worst_status(statuses: Iterable[QualityStatus]) -> QualityStatus:
    order = {QualityStatus.GOOD: 0, QualityStatus.WARNING: 1, QualityStatus.POOR: 2}
    worst = QualityStatus.GOOD
    for status in statuses:
        if order[status] > order[worst]:
            worst = status
    return worst


def _assess_resolution(shortest_side_px: int) -> _Indicator:
    if shortest_side_px < SHORT_SIDE_POOR_PX:
        return _Indicator(
            QualityStatus.POOR,
            f"Resolution is very low (shortest side {shortest_side_px}px). "
            "Text may be unreadable for verification.",
        )
    if shortest_side_px < SHORT_SIDE_WARNING_PX:
        return _Indicator(
            QualityStatus.WARNING,
            f"Resolution is modest (shortest side {shortest_side_px}px). "
            "A closer or higher-resolution photo may help.",
        )
    return _Indicator(QualityStatus.GOOD, None)


def _assess_blur(laplacian_variance: float) -> _Indicator:
    if laplacian_variance < LAPLACIAN_POOR:
        return _Indicator(
            QualityStatus.POOR,
            "The image appears very blurry. Hold the camera steady and refocus on the label.",
        )
    if laplacian_variance < LAPLACIAN_WARNING:
        return _Indicator(
            QualityStatus.WARNING,
            "The image may be slightly soft/blurry. A sharper photo may improve text reading.",
        )
    return _Indicator(QualityStatus.GOOD, None)


def _assess_brightness(mean_brightness: float) -> _Indicator:
    if mean_brightness < BRIGHTNESS_DARK_POOR:
        return _Indicator(
            QualityStatus.POOR,
            "The image is very dark. Increase lighting and avoid shadows on the label.",
        )
    if mean_brightness > BRIGHTNESS_BRIGHT_POOR:
        return _Indicator(
            QualityStatus.POOR,
            "The image is very bright / washed out. Reduce glare or exposure.",
        )
    if mean_brightness < BRIGHTNESS_DARK_WARNING:
        return _Indicator(
            QualityStatus.WARNING,
            "The image looks underexposed. Brighter, even lighting is recommended.",
        )
    if mean_brightness > BRIGHTNESS_BRIGHT_WARNING:
        return _Indicator(
            QualityStatus.WARNING,
            "The image looks overexposed. Watch for glare that washes out text.",
        )
    return _Indicator(QualityStatus.GOOD, None)


def _assess_contrast(contrast_std: float) -> _Indicator:
    if contrast_std < CONTRAST_POOR:
        return _Indicator(
            QualityStatus.POOR,
            "Contrast is very low. Text may blend into the background.",
        )
    if contrast_std < CONTRAST_WARNING:
        return _Indicator(
            QualityStatus.WARNING,
            "Contrast is somewhat low. Ensure the label is evenly lit.",
        )
    return _Indicator(QualityStatus.GOOD, None)


def _assess_clipping(near_black: float, near_white: float) -> _Indicator:
    clipped = max(near_black, near_white)
    if clipped >= CLIP_POOR_FRACTION:
        which = "dark" if near_black >= near_white else "bright"
        return _Indicator(
            QualityStatus.POOR,
            f"Severe {which} clipping detected. Detail in those regions may be lost.",
        )
    if clipped >= CLIP_WARNING_FRACTION:
        which = "dark" if near_black >= near_white else "bright"
        return _Indicator(
            QualityStatus.WARNING,
            f"Noticeable {which} clipping. Check for crushed shadows or glare.",
        )
    return _Indicator(QualityStatus.GOOD, None)
