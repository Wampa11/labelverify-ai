"""
Pydantic models for image upload analysis responses.

Architectural responsibility: typed contracts for validation, quality,
and dual image representations.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ImageFormat(StrEnum):
    """Formats accepted for label image upload in Phase 2."""

    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"


class QualityStatus(StrEnum):
    """Overall image-quality band for operator awareness (not regulatory certainty)."""

    GOOD = "GOOD"
    WARNING = "WARNING"
    POOR = "POOR"


class ImageValidationResult(BaseModel):
    """Outcome of server-side image validation."""

    accepted: bool
    detected_format: ImageFormat | None = None
    declared_content_type: str | None = None
    size_bytes: int
    message: str


class ImageMetadata(BaseModel):
    """Descriptive metadata for a validated label image."""

    original_filename: str | None = None
    format: ImageFormat
    width_px: int
    height_px: int
    mode: str = Field(description="Pillow color mode after orientation correction, e.g. RGB")
    size_bytes: int
    exif_orientation_applied: bool = False


class QualityMeasurements(BaseModel):
    """Raw quality measurements used to derive warnings and status."""

    width_px: int
    height_px: int
    shortest_side_px: int
    laplacian_variance: float = Field(
        description="Focus/blur proxy: variance of Laplacian on grayscale (higher ≈ sharper)",
    )
    mean_brightness: float = Field(description="Mean grayscale intensity in [0, 255]")
    contrast_std: float = Field(description="Std-dev of grayscale intensities")
    near_black_fraction: float = Field(
        description="Fraction of pixels with intensity <= clipping_low threshold",
    )
    near_white_fraction: float = Field(
        description="Fraction of pixels with intensity >= clipping_high threshold",
    )


class ImageQualityAssessment(BaseModel):
    """Explainable image-quality assessment for human operators."""

    status: QualityStatus
    measurements: QualityMeasurements
    warnings: list[str] = Field(default_factory=list)
    notes: str = Field(
        default=(
            "Quality indicators are engineering heuristics for OCR readiness awareness. "
            "They are not regulatory determinations."
        ),
    )


class PreprocessingOperation(BaseModel):
    """A single preprocessing step that was applied or considered."""

    name: str
    applied: bool
    detail: str


class PreprocessingSummary(BaseModel):
    """Summary of transformations producing display and OCR representations."""

    operations: list[PreprocessingOperation]
    deskew_applied: bool
    deskew_angle_degrees: float | None = None
    deskew_skipped_reason: str | None = None


class ImageAnalysisResponse(BaseModel):
    """Full response for POST /api/v1/images/analyze."""

    analysis_id: str = Field(
        description="Ephemeral workflow identifier for this request; not a persisted record",
    )
    validation: ImageValidationResult
    metadata: ImageMetadata
    quality: ImageQualityAssessment
    preprocessing: PreprocessingSummary
    display_image_base64: str = Field(
        description="Orientation-corrected image for UI preview (base64, no data: prefix)",
    )
    display_media_type: str
    ocr_image_base64: str = Field(
        description="OCR-prepared representation (base64, no data: prefix)",
    )
    ocr_media_type: str
    processing_time_ms: float
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    disclaimer: str = Field(
        default=(
            "Image analysis supports human review. Quality status is not a regulatory finding."
        ),
    )


class ImageUploadErrorBody(BaseModel):
    """User-facing error payload for rejected uploads."""

    error: str
    code: str
    details: str | None = None
