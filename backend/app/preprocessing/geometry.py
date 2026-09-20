"""
Geometry helpers and conservative deskew for label images.

Architectural responsibility: prepare for later perspective correction; apply only
low-risk deskew when the estimated angle is small and reliable. No bottle curvature correction.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class DeskewDecision:
    """Outcome of deskew estimation — applied only when confident."""

    applied: bool
    angle_degrees: float | None
    skipped_reason: str | None
    corrected_gray: np.ndarray | None


@dataclass(frozen=True)
class PerspectiveCorrectionPlan:
    """
    Placeholder for future four-point perspective correction.

    Phase 2 does not estimate or apply perspective warps automatically.
    """

    supported: bool = False
    reason: str = (
        "Automatic perspective / bottle-curvature correction is not implemented. "
        "Conservative planar deskew may still apply when angle confidence is high."
    )


def plan_perspective_correction() -> PerspectiveCorrectionPlan:
    """Return the current (non-implemented) perspective-correction capability."""
    return PerspectiveCorrectionPlan()


def estimate_skew_angle_degrees(gray: np.ndarray) -> tuple[float | None, str | None]:
    """
    Estimate planar skew via minimum-area rectangle on edge points.

    Returns (angle_degrees, skip_reason). Angle is the small correction to make text
    more horizontal. Returns (None, reason) when estimation is unreliable.
    """
    if gray.size == 0:
        return None, "empty_image"

    # Downsample large images for stable, fast estimation.
    working = gray
    height, width = gray.shape[:2]
    longest = max(height, width)
    if longest > 1200:
        scale = 1200 / float(longest)
        working = cv2.resize(
            gray,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    edges = cv2.Canny(working, 50, 150, apertureSize=3)
    coords = np.column_stack(np.where(edges > 0))
    if coords.shape[0] < 200:
        return None, "insufficient_edge_points"

    # np.where returns (row, col) → swap to (x, y) for minAreaRect
    points = np.fliplr(coords).astype(np.float32)
    rect = cv2.minAreaRect(points)
    angle = float(rect[-1])

    # OpenCV minAreaRect angle conventions vary; normalize to [-45, 45].
    if angle < -45:
        angle += 90
    elif angle > 45:
        angle -= 90

    # Prefer the smaller absolute rotation toward horizontal.
    if abs(angle) > 45:
        angle = angle - 90 if angle > 0 else angle + 90

    return angle, None


def maybe_deskew(gray: np.ndarray) -> DeskewDecision:
    """
    Apply deskew only for modest angles with enough edge evidence.

    Does not transform when |angle| < 0.5° (noise) or |angle| > 12° (risk of wrong warp).
    """
    angle, skip = estimate_skew_angle_degrees(gray)
    if skip is not None:
        return DeskewDecision(
            applied=False,
            angle_degrees=None,
            skipped_reason=skip,
            corrected_gray=None,
        )
    assert angle is not None
    if abs(angle) < 0.5:
        return DeskewDecision(
            applied=False,
            angle_degrees=angle,
            skipped_reason="angle_below_minimum_threshold",
            corrected_gray=None,
        )
    if abs(angle) > 12.0:
        return DeskewDecision(
            applied=False,
            angle_degrees=angle,
            skipped_reason="angle_above_safe_maximum",
            corrected_gray=None,
        )

    height, width = gray.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
    rotated = cv2.warpAffine(
        gray,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return DeskewDecision(
        applied=True,
        angle_degrees=angle,
        skipped_reason=None,
        corrected_gray=rotated,
    )
