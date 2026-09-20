"""
Structured label extraction models (not regulatory decisions).

Architectural responsibility: represent what the label appears to say —
FOUND / UNCERTAIN / NOT_FOUND — with OCR evidence for explainability.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExtractionStatus(StrEnum):
    """Outcome of structured field extraction (not regulatory PASS/REVIEW/FAIL)."""

    FOUND = "FOUND"
    UNCERTAIN = "UNCERTAIN"
    NOT_FOUND = "NOT_FOUND"


class ExtractionMethod(StrEnum):
    """How a field value was obtained."""

    REGEX = "regex"
    LAYOUT_HEURISTIC = "layout_heuristic"
    TERMINOLOGY_MATCH = "terminology_match"
    COMBINED = "combined"
    NOT_EXTRACTED = "not_extracted"


class OcrRegionRef(BaseModel):
    """Reference to OCR evidence used for a field (coordinates in OCR image space)."""

    text: str
    confidence: float | None = None
    bounding_box: dict[str, Any] | None = None
    provider_name: str | None = None
    preprocessing_profile: str | None = None


class ExtractedField(BaseModel):
    """One structured field extracted from OCR evidence."""

    field_name: str
    status: ExtractionStatus
    raw_text: str | None = None
    normalized_value: str | None = Field(
        default=None,
        description="Structured/normalized form when applicable; never drops raw_text",
    )
    normalized_numeric: float | None = None
    normalized_unit: str | None = None
    candidates: list[str] = Field(default_factory=list)
    ocr_regions: list[OcrRegionRef] = Field(default_factory=list)
    extraction_method: ExtractionMethod = ExtractionMethod.NOT_EXTRACTED
    explanation: str
    # Reserved for future AI fallback packaging (unused in Phase 4).
    ai_fallback_hints: dict[str, Any] = Field(default_factory=dict)


class OcrPassSummary(BaseModel):
    """Observable summary of one OCR+extraction pass (FAST or ENHANCED)."""

    profile: str
    max_edge_px: int
    provider_name: str
    preprocessing_time_ms: float
    ocr_time_ms: float
    extraction_time_ms: float
    total_pass_time_ms: float
    ocr_text_preview: str
    word_count: int
    image_width_px: int | None = None
    image_height_px: int | None = None
    fields: dict[str, ExtractedField]
    found_count: int
    uncertain_count: int
    not_found_count: int


class RetryDecision(BaseModel):
    """Whether and why an ENHANCED OCR retry was triggered."""

    triggered: bool
    reasons: list[str] = Field(default_factory=list)
    performed: bool = False


class ResultSelection(BaseModel):
    """Which OCR pass was selected and why."""

    selected_profile: str
    reason: str
    fast_score: int | None = None
    enhanced_score: int | None = None


class BrandEscalationSummary(BaseModel):
    """Observable selective brand OCR escalation (region / optional secondary)."""

    triggered: bool = False
    triggers: list[str] = Field(default_factory=list)
    region_method: str | None = None
    tesseract_region_ran: bool = False
    tesseract_region_ms: float | None = None
    secondary_ran: bool = False
    secondary_provider: str | None = None
    secondary_ms: float | None = None
    secondary_skipped_reason: str | None = None
    reconcile_outcomes: list[str] = Field(default_factory=list)
    evidence_method_suffix: str | None = None
    whole_brand_raw: str | None = None
    region_brand_raw: str | None = None
    secondary_brand_raw: str | None = None


class ExtractedLabelResult(BaseModel):
    """Final structured extraction for one label image (Single Review)."""

    analysis_id: str
    selected_fields: dict[str, ExtractedField]
    fast_pass: OcrPassSummary
    enhanced_pass: OcrPassSummary | None = None
    retry: RetryDecision
    selection: ResultSelection
    brand_escalation: BrandEscalationSummary | None = None
    ocr_image_width_px: int | None = None
    ocr_image_height_px: int | None = None
    display_image_width_px: int | None = None
    display_image_height_px: int | None = None
    # Regions for UI highlight are in OCR image coordinates of the selected pass.
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    processing_time_ms: float
    disclaimer: str = Field(
        default=(
            "Extraction only: these values describe what the label appears to say. "
            "This is not a regulatory compliance determination."
        ),
    )


class LabelExtractionResponse(BaseModel):
    """API response combining display analysis artifacts with structured extraction."""

    # Reuse display/quality from image analysis without regulatory checks.
    analysis_id: str
    filename: str | None = None
    display_image_base64: str
    display_media_type: str
    metadata_width_px: int
    metadata_height_px: int
    quality_status: str
    quality_warnings: list[str] = Field(default_factory=list)
    extraction: ExtractedLabelResult
    processing_time_ms: float
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    disclaimer: str = (
        "Decision support only. Extraction is not a final regulatory determination."
    )
