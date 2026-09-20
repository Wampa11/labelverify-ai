"""
Deterministic ENHANCED OCR retry policy and FAST vs ENHANCED result selection.

Architectural responsibility: observable retry triggers and transparent pass selection.
"""

from __future__ import annotations

from app.models.extraction import (
    ExtractedField,
    ExtractionStatus,
    OcrPassSummary,
    ResultSelection,
    RetryDecision,
)
from app.models.image_analysis import QualityStatus
from app.normalization.comparison import prefer_agreeing_text, text_candidates_agree

CRITICAL_FIELDS = (
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "government_warning",
)


def should_retry_enhanced(
    fields: dict[str, ExtractedField],
    *,
    ocr_text: str,
    word_count: int,
    quality_status: QualityStatus | str | None,
) -> RetryDecision:
    """
    Decide whether one ENHANCED/1200 retry should run after FAST extraction.

    Does not retry solely because quality is not GOOD.
    """
    reasons: list[str] = []
    warning = fields.get("government_warning")
    if warning and warning.status == ExtractionStatus.NOT_FOUND:
        reasons.append("government_warning_not_found")

    not_found = sum(
        1
        for name in CRITICAL_FIELDS
        if fields.get(name) and fields[name].status == ExtractionStatus.NOT_FOUND
    )
    if not_found >= 2:
        reasons.append(f"critical_fields_not_found={not_found}")

    uncertain = sum(
        1
        for name in CRITICAL_FIELDS
        if fields.get(name) and fields[name].status == ExtractionStatus.UNCERTAIN
    )
    quality = str(quality_status) if quality_status is not None else ""
    if (
        uncertain >= 2
        and not_found >= 1
        and quality in {QualityStatus.WARNING.value, QualityStatus.POOR.value, "WARNING", "POOR"}
    ):
        reasons.append("uncertain_fields_with_quality_issue_and_missing_field")

    useful_chars = len((ocr_text or "").strip())
    # Sparse OCR: little recoverable text. Do not treat empty word geometry alone
    # as sparse when full_text is already substantial (scripted/tests may omit words).
    if useful_chars < 20 or (word_count < 3 and useful_chars < 80):
        reasons.append("ocr_text_unusually_sparse")

    return RetryDecision(triggered=bool(reasons), reasons=reasons, performed=False)


def score_pass(fields: dict[str, ExtractedField]) -> int:
    """Score FOUND=2, UNCERTAIN=1, NOT_FOUND=0 across critical fields."""
    total = 0
    for name in CRITICAL_FIELDS:
        field = fields.get(name)
        if field is None:
            continue
        if field.status == ExtractionStatus.FOUND:
            total += 2
        elif field.status == ExtractionStatus.UNCERTAIN:
            total += 1
    return total


def select_pass(
    fast: OcrPassSummary,
    enhanced: OcrPassSummary | None,
) -> ResultSelection:
    """
    Prefer the pass with better extraction completeness; do not blindly prefer ENHANCED.
    """
    fast_score = score_pass(fast.fields)
    if enhanced is None:
        return ResultSelection(
            selected_profile=fast.profile,
            reason="Only FAST pass available.",
            fast_score=fast_score,
            enhanced_score=None,
        )

    enhanced_score = score_pass(enhanced.fields)
    if enhanced_score > fast_score:
        return ResultSelection(
            selected_profile=enhanced.profile,
            reason=(
                f"ENHANCED scored higher on field completeness "
                f"({enhanced_score} > {fast_score})."
            ),
            fast_score=fast_score,
            enhanced_score=enhanced_score,
        )
    if enhanced_score < fast_score:
        return ResultSelection(
            selected_profile=fast.profile,
            reason=(
                f"FAST scored higher or equal on field completeness "
                f"({fast_score} >= {enhanced_score}); keeping FAST."
            ),
            fast_score=fast_score,
            enhanced_score=enhanced_score,
        )

    # Tie: prefer fewer NOT_FOUND, then FAST for latency.
    fast_nf = sum(1 for f in fast.fields.values() if f.status == ExtractionStatus.NOT_FOUND)
    enh_nf = sum(1 for f in enhanced.fields.values() if f.status == ExtractionStatus.NOT_FOUND)
    if enh_nf < fast_nf:
        return ResultSelection(
            selected_profile=enhanced.profile,
            reason="Scores tied; ENHANCED has fewer NOT_FOUND fields.",
            fast_score=fast_score,
            enhanced_score=enhanced_score,
        )
    return ResultSelection(
        selected_profile=fast.profile,
        reason="Scores tied; preferring FAST for lower latency.",
        fast_score=fast_score,
        enhanced_score=enhanced_score,
    )


def merge_conflicts_as_uncertain(
    selected: dict[str, ExtractedField],
    other: dict[str, ExtractedField] | None,
) -> dict[str, ExtractedField]:
    """
    If the alternate pass disagrees on normalized numeric/value for a FOUND field,
    mark the selected field UNCERTAIN and note the conflict.
    """
    if other is None:
        return selected
    merged = dict(selected)
    for name, field in selected.items():
        alt = other.get(name)
        if alt is None:
            continue
        if field.status != ExtractionStatus.FOUND or alt.status != ExtractionStatus.FOUND:
            continue
        if field.normalized_numeric is not None and alt.normalized_numeric is not None:
            if abs(field.normalized_numeric - alt.normalized_numeric) > 1e-6:
                merged[name] = field.model_copy(
                    update={
                        "status": ExtractionStatus.UNCERTAIN,
                        "candidates": list(
                            dict.fromkeys(
                                [
                                    *(field.candidates or []),
                                    field.raw_text or "",
                                    alt.raw_text or "",
                                ],
                            ),
                        ),
                        "explanation": (
                            field.explanation
                            + f" Conflict with alternate pass value {alt.normalized_value!r}; "
                            "marked uncertain."
                        ),
                    },
                )
        elif name in {"brand_name", "class_type"} and (
            field.normalized_value or field.raw_text
        ) and (alt.normalized_value or alt.raw_text):
            left = field.normalized_value or field.raw_text
            right = alt.normalized_value or alt.raw_text
            if text_candidates_agree(left, right):
                # Noisy alternate (e.g. "di BOURBON WHISKEY") must not demote a
                # clean FAST FOUND when normalized evidence still agrees.
                cleaner = prefer_agreeing_text(left, right) or left
                if cleaner != field.normalized_value:
                    merged[name] = field.model_copy(
                        update={
                            "normalized_value": cleaner,
                            "raw_text": prefer_agreeing_text(field.raw_text, alt.raw_text)
                            or field.raw_text,
                            "candidates": list(
                                dict.fromkeys(
                                    [
                                        *(field.candidates or []),
                                        field.raw_text or "",
                                        alt.raw_text or "",
                                    ],
                                ),
                            ),
                            "explanation": (
                                field.explanation
                                + " Alternate pass agreed after normalization; "
                                "kept stronger/cleaner candidate."
                            ),
                        },
                    )
                continue
            if (
                field.normalized_value
                and alt.normalized_value
                and field.normalized_value.strip().lower()
                != alt.normalized_value.strip().lower()
            ):
                merged[name] = field.model_copy(
                    update={
                        "status": ExtractionStatus.UNCERTAIN,
                        "candidates": list(
                            dict.fromkeys(
                                [
                                    *(field.candidates or []),
                                    field.raw_text or "",
                                    alt.raw_text or "",
                                ],
                            ),
                        ),
                        "explanation": (
                            field.explanation
                            + " Alternate pass proposed a different text candidate; "
                            "marked uncertain."
                        ),
                    },
                )
    return merged
