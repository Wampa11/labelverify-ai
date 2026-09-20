"""
Structured AI evidence contracts for optional vision fallback.

Architectural responsibility: evidence-only schemas — never regulatory PASS/REVIEW/FAIL.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AiEvidenceConfidence(StrEnum):
    """Bounded AI evidence confidence — not regulatory certainty."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AiFieldEvidence(BaseModel):
    """One field's recovered evidence from vision assistance."""

    field: str
    candidate_value: str | None = None
    raw_observed_text: str | None = None
    confidence: AiEvidenceConfidence = AiEvidenceConfidence.LOW
    evidence_description: str = ""
    unable_to_determine: bool = False
    source_region_if_available: dict[str, Any] | None = None


class AiEvidenceRequestItem(BaseModel):
    """One unresolved field included in an AI evidence package."""

    field: str
    reason_code: str
    task_instruction: str
    ocr_text: str | None = None
    candidates: list[str] = Field(default_factory=list)
    application_value: str | None = None
    extraction_status: str | None = None
    extraction_explanation: str | None = None


class AiEvidencePackage(BaseModel):
    """
    Minimum evidence sent to the AI provider for one review.

    Image bytes stay out of JSON logs; callers pass image separately to the provider.
    """

    fields: list[AiEvidenceRequestItem]
    quality_status: str | None = None
    quality_warnings: list[str] = Field(default_factory=list)
    uses_full_image: bool = True
    crop_note: str | None = None
    # Prompt-injection defense reminder is always applied by the provider.


class AiEvidenceBatchResult(BaseModel):
    """Validated AI batch response for one review call."""

    availability: str
    provider_name: str
    model: str | None = None
    fields: list[AiFieldEvidence] = Field(default_factory=list)
    explanation: str
    latency_ms: float | None = None
    raw_error: str | None = None
    called: bool = False


class AiAssistSummary(BaseModel):
    """Observable AI assist summary attached to a verification response."""

    attempted: bool = False
    called: bool = False
    provider_name: str | None = None
    model: str | None = None
    trigger_reason_codes: list[str] = Field(default_factory=list)
    fields_requested: list[str] = Field(default_factory=list)
    fields_updated: list[str] = Field(default_factory=list)
    fields_proposed: list[str] = Field(default_factory=list)
    merge_outcomes: dict[str, str] = Field(default_factory=dict)
    latency_ms: float | None = None
    outcome: str = "not_attempted"
    explanation: str = ""
    status_before: str | None = None
    status_after: str | None = None
    evidence_changed: bool = False
    # Runtime diagnostics (never secrets)
    ai_configured: bool = False
    ai_eligible: bool = False
    eligible_fields: list[str] = Field(default_factory=list)
    ai_succeeded: bool = False
    failure_category: str | None = None
    evidence_method: str = "ocr_only"
