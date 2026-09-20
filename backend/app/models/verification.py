"""
Verification result models shared across the pipeline and API.

Architectural responsibility:
explainable PASS/REVIEW/FAIL outcomes with timing and decision metadata.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.extraction import ExtractedLabelResult


class CheckStatus(StrEnum):
    """Allowed outcomes for every verification check."""

    PASS = "PASS"
    REVIEW = "REVIEW"
    FAIL = "FAIL"


class DecisionMethod(StrEnum):
    """How a check decision was produced (for explainability)."""

    DETERMINISTIC_RULE = "deterministic_rule"
    FUZZY_MATCH = "fuzzy_match"
    NORMALIZED_COMPARISON = "normalized_comparison"
    CONFIDENCE_POLICY = "confidence_policy"
    AI_ASSIST = "ai_assist"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    NOT_EVALUATED = "not_evaluated"
    PIPELINE_STUB = "pipeline_stub"


class ReviewReasonCode(StrEnum):
    """
    Machine-readable reason codes for Phase 6 AI eligibility triage.

    Not every REVIEW is AI-eligible; formatting/vision limits should stay human-only.
    """

    BRAND_MATCH = "BRAND_MATCH"
    BRAND_MISMATCH = "BRAND_MISMATCH"
    BRAND_AMBIGUOUS = "BRAND_AMBIGUOUS"
    CLASS_TYPE_MATCH = "CLASS_TYPE_MATCH"
    CLASS_TYPE_MISMATCH = "CLASS_TYPE_MISMATCH"
    CLASS_TYPE_AMBIGUOUS = "CLASS_TYPE_AMBIGUOUS"
    ABV_MATCH = "ABV_MATCH"
    ABV_MISMATCH = "ABV_MISMATCH"
    ABV_FORMAT_REVIEW = "ABV_FORMAT_REVIEW"
    PROOF_ONLY_NO_PERCENT_STATEMENT = "PROOF_ONLY_NO_PERCENT_STATEMENT"
    NET_CONTENTS_MATCH = "NET_CONTENTS_MATCH"
    NET_CONTENTS_MISMATCH = "NET_CONTENTS_MISMATCH"
    WARNING_PRESENT_MATCH = "WARNING_PRESENT_MATCH"
    WARNING_MISSING = "WARNING_MISSING"
    WARNING_PARTIAL = "WARNING_PARTIAL"
    WARNING_WORDING_MISMATCH = "WARNING_WORDING_MISMATCH"
    WARNING_CAPS_REVIEW = "WARNING_CAPS_REVIEW"
    FORMAT_NOT_MACHINE_VERIFIABLE = "FORMAT_NOT_MACHINE_VERIFIABLE"
    EXTRACTION_UNCERTAIN = "EXTRACTION_UNCERTAIN"
    EXTRACTION_NOT_FOUND = "EXTRACTION_NOT_FOUND"
    APPLICATION_VALUE_MISSING = "APPLICATION_VALUE_MISSING"
    APPLICATION_VALUE_INVALID = "APPLICATION_VALUE_INVALID"
    OCR_LOW_QUALITY = "OCR_LOW_QUALITY"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    NOT_MACHINE_VERIFIABLE = "NOT_MACHINE_VERIFIABLE"


class DetectionSource(BaseModel):
    """Where a detected label value came from."""

    detector: str = Field(description="e.g. ocr, extractor, manual")
    raw_text: str | None = None
    bounding_box: dict[str, Any] | None = Field(
        default=None,
        description="Optional geometry from OCR/layout; schema left flexible for later OCR choice",
    )
    notes: str | None = None


class FieldCheckResult(BaseModel):
    """Outcome of a single field or regulatory check."""

    rule_id: str | None = Field(default=None, description="Stable rule id from docs/RULES.md")
    check_name: str
    application_value: str | None = None
    detected_label_value: str | None = None
    expected_value: str | None = Field(
        default=None,
        description="What was expected (application value or statutory text summary)",
    )
    normalized_application_value: str | None = None
    normalized_detected_value: str | None = None
    status: CheckStatus
    confidence: float | None = Field(
        default=None,
        description="Only set when actually measured; never invent a value",
        ge=0.0,
        le=1.0,
    )
    explanation: str
    decision_method: DecisionMethod
    reason_code: str | None = Field(
        default=None,
        description="Machine-readable reason for Phase 6 triage / analytics",
    )
    ai_assist_eligible: bool = Field(
        default=False,
        description="Whether Phase 6 may consider AI assist (False for vision/format limits)",
    )
    limitations: list[str] = Field(default_factory=list)
    technical_details: dict[str, Any] = Field(
        default_factory=dict,
        description="Similarity scores and other engineering details — not regulatory certainty",
    )
    detection_source: DetectionSource | None = None
    processing_time_ms: float | None = Field(
        default=None,
        description="Optional per-check timing when measured",
    )
    authoritative_sources: list[str] = Field(
        default_factory=list,
        description="Citation strings for the check (from regulatory_sources)",
    )


class VerificationResult(BaseModel):
    """Full result of verifying one label (optionally against an application)."""

    verification_id: str | None = None
    product_class: str = Field(default="distilled_spirits")
    verification_mode: str = Field(
        default="application_comparison",
        description="label_only | application_comparison",
    )
    overall_status: CheckStatus
    checks: list[FieldCheckResult]
    pass_count: int = 0
    review_count: int = 0
    fail_count: int = 0
    processing_time_ms: float = Field(
        description="Required wall-clock pipeline duration in milliseconds",
    )
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    ai_used: bool = False
    ai_degraded: bool = Field(
        default=False,
        description="True when AI was desired but skipped/unavailable (observable degradation)",
    )
    ai_assist: dict[str, Any] | None = Field(
        default=None,
        description="Observable AI evidence-recovery summary (never a regulatory decision)",
    )
    degradation_notes: list[str] = Field(default_factory=list)
    disclaimer: str = Field(
        default=(
            "Decision support only. LabelVerify AI does not make final regulatory determinations. "
            "A qualified human must review ambiguous results."
        ),
    )


class SingleReviewVerificationResponse(BaseModel):
    """
    Combined Single Review response: display preview, extraction, and verification.

    Extraction statuses remain FOUND/UNCERTAIN/NOT_FOUND; verification uses PASS/REVIEW/FAIL.
    """

    analysis_id: str
    verification_id: str
    filename: str | None = None
    verification_mode: str = Field(
        default="label_only",
        description="label_only (Single Review) or application_comparison (Batch / optional)",
    )
    application: ApplicationData | None = Field(
        default=None,
        description="Present only when application-comparison mode supplied application values",
    )
    display_image_base64: str
    display_media_type: str
    metadata_width_px: int
    metadata_height_px: int
    quality_status: str
    quality_warnings: list[str] = Field(default_factory=list)
    extraction: ExtractedLabelResult
    verification: VerificationResult
    processing_time_ms: float
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    disclaimer: str = (
        "Decision support only. LabelVerify AI does not make final regulatory determinations. "
        "Overall status is a prototype verification summary for human review."
    )


class ApplicationData(BaseModel):
    """
    Application-side values supplied for comparison (initial spirits fields).

    Government health warning is label-only and is intentionally omitted.
    Additional fields may be added later without breaking existing clients.
    """

    brand_name: str = Field(..., min_length=1, max_length=200)
    class_type: str = Field(..., min_length=1, max_length=200)
    alcohol_content_abv: str = Field(..., min_length=1, max_length=50)
    net_contents: str = Field(..., min_length=1, max_length=50)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("brand_name", "class_type", "alcohol_content_abv", "net_contents")
    @classmethod
    def strip_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value is required")
        return cleaned

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
