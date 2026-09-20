"""
Shared helpers for building FieldCheckResult from extraction evidence.

Architectural responsibility: keep rule modules free of OCR/OpenAI SDKs.
"""

from __future__ import annotations

from app.models.extraction import ExtractedField, ExtractionStatus
from app.models.verification import (
    CheckStatus,
    DecisionMethod,
    DetectionSource,
    FieldCheckResult,
    ReviewReasonCode,
)

_FIELD_UNCERTAIN_MESSAGES: dict[str, str] = {
    "brand_name": "Brand name could not be reliably extracted.",
    "class_type": "Class/type could not be reliably extracted.",
    "alcohol_content": "Alcohol content could not be reliably extracted.",
    "net_contents": "Net contents could not be reliably extracted.",
    "government_warning": "Government warning text could not be reliably recovered.",
}

_FIELD_NOT_FOUND_MESSAGES: dict[str, str] = {
    "brand_name": "Brand name was not found on the label.",
    "class_type": "Class/type was not found on the label.",
    "alcohol_content": "Alcohol content could not be reliably extracted.",
    "net_contents": "Net contents could not be reliably extracted.",
    "government_warning": "Government warning text could not be reliably recovered.",
}


def detection_from_field(field: ExtractedField | None) -> DetectionSource | None:
    """Build DetectionSource from an extracted field when present."""
    if field is None:
        return None
    box = None
    if field.ocr_regions:
        box = field.ocr_regions[0].bounding_box
    return DetectionSource(
        detector="extractor",
        raw_text=field.raw_text,
        bounding_box=box,
        notes=field.extraction_method.value if field.extraction_method else None,
    )


def display_detected_value(field: ExtractedField | None) -> str | None:
    """Prefer normalized display value; keep raw OCR for technical details."""
    if field is None:
        return None
    return field.normalized_value or field.raw_text


def extraction_gate(
    *,
    rule_id: str,
    check_name: str,
    application_value: str | None,
    field: ExtractedField | None,
    sources: list[str],
    quality_status: str | None = None,
) -> FieldCheckResult | None:
    """
    Return a REVIEW result when extraction is UNCERTAIN/NOT_FOUND or missing.
    Otherwise return None so the rule can continue.
    """
    if field is None:
        return FieldCheckResult(
            rule_id=rule_id,
            check_name=check_name,
            application_value=application_value,
            expected_value=application_value,
            detected_label_value=None,
            status=CheckStatus.REVIEW,
            explanation="No extraction evidence was available for this field.",
            decision_method=DecisionMethod.HUMAN_REVIEW_REQUIRED,
            reason_code=ReviewReasonCode.EXTRACTION_NOT_FOUND.value,
            ai_assist_eligible=True,
            authoritative_sources=sources,
        )
    if field.status == ExtractionStatus.UNCERTAIN:
        semantic_reason = ReviewReasonCode.EXTRACTION_UNCERTAIN.value
        hints = field.ai_fallback_hints or {}
        if hints.get("reason_code_hint") == "CONFLICTING_EVIDENCE" or hints.get("ai_conflict"):
            semantic_reason = ReviewReasonCode.CONFLICTING_EVIDENCE.value
        elif hints.get("reason") == "brand_ambiguous":
            semantic_reason = ReviewReasonCode.BRAND_AMBIGUOUS.value
        elif hints.get("reason") == "brand_ocr_conflict":
            semantic_reason = ReviewReasonCode.CONFLICTING_EVIDENCE.value
        explanation = _FIELD_UNCERTAIN_MESSAGES.get(
            field.field_name,
            "Label extraction for this field is uncertain; human review is required.",
        )
        display_reason = semantic_reason
        if (
            quality_status in {"WARNING", "POOR"}
            and semantic_reason == ReviewReasonCode.EXTRACTION_UNCERTAIN.value
        ):
            display_reason = ReviewReasonCode.OCR_LOW_QUALITY.value
            explanation = f"{explanation} Image quality status was {quality_status}."
        return FieldCheckResult(
            rule_id=rule_id,
            check_name=check_name,
            application_value=application_value,
            expected_value=application_value,
            detected_label_value=display_detected_value(field),
            status=CheckStatus.REVIEW,
            explanation=explanation,
            decision_method=DecisionMethod.HUMAN_REVIEW_REQUIRED,
            reason_code=display_reason,
            ai_assist_eligible=True,
            detection_source=detection_from_field(field),
            authoritative_sources=sources,
            technical_details={
                "extraction_status": field.status.value,
                "underlying_reason_code": semantic_reason,
                "quality_status": quality_status,
                "extractor_explanation": field.explanation,
                "raw_ocr": field.raw_text,
                "normalized_value": field.normalized_value,
                "extraction_method": field.extraction_method.value,
                "ai_fallback_hints": field.ai_fallback_hints,
            },
        )
    if field.status == ExtractionStatus.NOT_FOUND:
        semantic_reason = ReviewReasonCode.EXTRACTION_NOT_FOUND.value
        explanation = _FIELD_NOT_FOUND_MESSAGES.get(
            field.field_name,
            "The field was not found on the label by extraction.",
        )
        if field.field_name == "government_warning":
            semantic_reason = ReviewReasonCode.WARNING_MISSING.value
        # Quality may explain why OCR missed the field; it must not block AI recovery.
        display_reason = semantic_reason
        if quality_status in {"WARNING", "POOR"}:
            display_reason = ReviewReasonCode.OCR_LOW_QUALITY.value
            explanation = (
                f"{explanation} Image quality status was {quality_status}."
            )
        return FieldCheckResult(
            rule_id=rule_id,
            check_name=check_name,
            application_value=application_value,
            expected_value=application_value,
            detected_label_value=None,
            status=CheckStatus.REVIEW,
            explanation=explanation,
            decision_method=DecisionMethod.HUMAN_REVIEW_REQUIRED,
            reason_code=display_reason,
            ai_assist_eligible=True,
            detection_source=detection_from_field(field),
            authoritative_sources=sources,
            technical_details={
                "extraction_status": field.status.value,
                "underlying_reason_code": semantic_reason,
                "quality_status": quality_status,
                "extractor_explanation": field.explanation,
            },
        )
    return None
