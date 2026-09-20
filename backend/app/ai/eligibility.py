"""
Eligibility policy for optional AI evidence recovery.

Architectural responsibility: decide which REVIEW checks may invoke AI —
field-aware and based on underlying extraction/semantic conditions.
OCR_LOW_QUALITY explains OCR difficulty; it must not alone block recovery
when the underlying field state is otherwise AI-eligible.
"""

from __future__ import annotations

from app.models.verification import CheckStatus, FieldCheckResult, ReviewReasonCode

# Explicit allowlist of semantic reasons that may invoke AI.
ELIGIBLE_REASON_CODES: frozenset[str] = frozenset(
    {
        ReviewReasonCode.BRAND_AMBIGUOUS.value,
        ReviewReasonCode.CLASS_TYPE_AMBIGUOUS.value,
        ReviewReasonCode.WARNING_PARTIAL.value,
        ReviewReasonCode.WARNING_MISSING.value,
        ReviewReasonCode.EXTRACTION_UNCERTAIN.value,
        ReviewReasonCode.EXTRACTION_NOT_FOUND.value,
        ReviewReasonCode.ABV_FORMAT_REVIEW.value,
        ReviewReasonCode.PROOF_ONLY_NO_PERCENT_STATEMENT.value,
        ReviewReasonCode.CONFLICTING_EVIDENCE.value,
    },
)

# Never AI-promoted as formatting/physical certification questions.
HUMAN_ONLY_REASON_CODES: frozenset[str] = frozenset(
    {
        ReviewReasonCode.FORMAT_NOT_MACHINE_VERIFIABLE.value,
        ReviewReasonCode.NOT_MACHINE_VERIFIABLE.value,
        ReviewReasonCode.WARNING_CAPS_REVIEW.value,
    },
)

CHECK_TO_FIELD: dict[str, str] = {
    "Brand Name": "brand_name",
    "Class / Type": "class_type",
    "Alcohol Content / ABV": "alcohol_content",
    "Net Contents": "net_contents",
    "Government Health Warning": "government_warning",
}

FIELD_TASKS: dict[str, str] = {
    "brand_name": (
        "Independently inspect the label IMAGE and identify the brand name text "
        "visibly printed on it. OCR context may be incomplete or wrong — do not simply "
        "echo it. Return the most complete multi-word brand visible. Evidence only; "
        "do not decide compliance."
    ),
    "class_type": (
        "Independently inspect the label IMAGE for the class/type designation "
        "(for example bourbon whiskey, vodka). Do not merely repeat OCR if the image "
        "shows a clearer reading. Return structured observed text only; no compliance "
        "decision."
    ),
    "alcohol_content": (
        "Independently inspect the label IMAGE for alcohol statements. Look for "
        "percentage alcohol by volume (including '% Alc./Vol.', 'Alc/Vol', 'ABV', or "
        "equivalent) AND any proof statement. If BOTH are visible, return a candidate "
        "that preserves both (for example '45% ALC./VOL. (90 PROOF)'). Do not stop "
        "searching after seeing proof alone in OCR context. Do NOT invent or calculate "
        "ABV from proof if the percentage statement is not visually present. Evidence "
        "only; no compliance decision."
    ),
    "net_contents": (
        "Independently inspect the label IMAGE for the net contents / volume statement "
        "(for example 750 mL or 1 L). Return quantity and unit only — do not include "
        "nearby proof or ABV text. Do not merely echo noisy OCR. Evidence only; no "
        "compliance decision."
    ),
    "government_warning": (
        "Independently inspect the label IMAGE for the government health warning block. "
        "Transcribe visible warning text (header and body) as completely as readable. "
        "Do NOT certify physical type size, bold weight, characters-per-inch, or final "
        "regulatory compliance. If unreadable, set unable_to_determine=true."
    ),
}


def is_eligible_reason(reason_code: str | None) -> bool:
    """True when the reason code is an explicitly AI-eligible semantic reason."""
    if not reason_code:
        return False
    if reason_code in HUMAN_ONLY_REASON_CODES:
        return False
    return reason_code in ELIGIBLE_REASON_CODES


def underlying_eligible_reason(check: FieldCheckResult) -> str | None:
    """
    Resolve the semantic AI-eligibility reason for a REVIEW check.

    OCR_LOW_QUALITY may appear as the display reason_code when image quality is
    poor, but recovery remains allowed when technical details (or field identity)
    show an underlying recoverable extraction condition.
    """
    if check.status != CheckStatus.REVIEW:
        return None
    if check.reason_code in HUMAN_ONLY_REASON_CODES:
        return None
    if is_eligible_reason(check.reason_code):
        return check.reason_code

    details = check.technical_details or {}
    semantic = details.get("underlying_reason_code") or details.get("semantic_reason_code")
    if isinstance(semantic, str) and is_eligible_reason(semantic):
        return semantic

    # Unwrap OCR_LOW_QUALITY only when underlying extraction state is recorded.
    # OCR_LOW_QUALITY alone (no semantic/extraction details) stays ineligible.
    if check.reason_code == ReviewReasonCode.OCR_LOW_QUALITY.value:
        extraction_status = details.get("extraction_status")
        field = CHECK_TO_FIELD.get(check.check_name)
        if extraction_status == "UNCERTAIN":
            return ReviewReasonCode.EXTRACTION_UNCERTAIN.value
        if extraction_status == "NOT_FOUND":
            if field == "government_warning":
                return ReviewReasonCode.WARNING_MISSING.value
            return ReviewReasonCode.EXTRACTION_NOT_FOUND.value
    return None


def collect_eligible_checks(
    checks: list[FieldCheckResult],
    *,
    overall_status: CheckStatus,
) -> list[FieldCheckResult]:
    """
    Return REVIEW checks eligible for AI evidence recovery.

    No AI when overall PASS or FAIL. Human-only formatting reasons never qualify.
    OCR_LOW_QUALITY alone does not qualify, but OCR_LOW_QUALITY that masks an
    underlying recoverable field state does.
    """
    if overall_status != CheckStatus.REVIEW:
        return []
    eligible: list[FieldCheckResult] = []
    for check in checks:
        if check.status != CheckStatus.REVIEW:
            continue
        if check.check_name not in CHECK_TO_FIELD:
            continue
        field = CHECK_TO_FIELD[check.check_name]
        if field not in FIELD_TASKS:
            continue
        # Prefer explicit flag when True; still allow unwrap when False solely due
        # to OCR_LOW_QUALITY masking (legacy gate behavior).
        if (
            not check.ai_assist_eligible
            and check.reason_code != ReviewReasonCode.OCR_LOW_QUALITY.value
        ):
            continue
        if underlying_eligible_reason(check) is None:
            continue
        eligible.append(check)
    return eligible
