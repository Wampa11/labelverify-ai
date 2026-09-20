"""
Validate and merge AI evidence into extracted fields.

Architectural responsibility: conservative reconciliation — never erase deterministic
evidence silently, never invent regulatory status. Conflicts → UNCERTAIN.
"""

from __future__ import annotations

from app.ai.evidence import AiEvidenceBatchResult, AiEvidenceConfidence, AiFieldEvidence
from app.models.extraction import ExtractedField, ExtractionMethod, ExtractionStatus
from app.normalization.comparison import comparison_normalize
from app.normalization.field_parsers import (
    alcohol_normalized_display,
    parse_alcohol_content,
    parse_net_contents,
)


def validate_field_evidence(item: AiFieldEvidence) -> tuple[bool, str]:
    """Return (ok, reason) after schema/plausibility checks."""
    if item.unable_to_determine:
        return False, "unable_to_determine"
    if not item.candidate_value and not item.raw_observed_text:
        return False, "empty_candidate"
    if item.confidence == AiEvidenceConfidence.LOW:
        return False, "low_confidence"
    text = (item.candidate_value or item.raw_observed_text or "").strip()
    if not text:
        return False, "empty_text"
    if item.field == "alcohol_content":
        parsed = parse_alcohol_content(text)
        if parsed is None or parsed.abv_percent is None:
            return False, "abv_unparseable"
        # Visible percent statement required — do not accept proof-only derivation.
        if parsed.source == "proof":
            return False, "abv_unparseable"
    if item.field == "net_contents":
        if parse_net_contents(text) is None:
            return False, "net_contents_unparseable"
    return True, "ok"


def merge_ai_evidence(
    fields: dict[str, ExtractedField],
    batch: AiEvidenceBatchResult,
) -> tuple[dict[str, ExtractedField], list[str], list[str], dict[str, str]]:
    """
    Merge validated AI candidates into a copy of extracted fields.

    Returns (merged_fields, updated_field_names, conflict_notes, merge_outcomes).
    """
    merged = {name: field.model_copy(deep=True) for name, field in fields.items()}
    updated: list[str] = []
    conflicts: list[str] = []
    outcomes: dict[str, str] = {}

    for item in batch.fields:
        ok, reason = validate_field_evidence(item)
        if not ok:
            outcomes[item.field] = f"rejected:{reason}"
            continue
        existing = merged.get(item.field)
        if existing is None:
            outcomes[item.field] = "rejected:unknown_field"
            continue
        text = (item.candidate_value or item.raw_observed_text or "").strip()

        if existing.status == ExtractionStatus.FOUND:
            if _mutually_reinforcing(existing, text, item.field):
                merged[item.field] = _apply_supplement(existing, item, text)
                updated.append(item.field)
                outcomes[item.field] = "supplemented"
                continue
            if _material_conflict(existing, text, item.field):
                conflicts.append(
                    f"{item.field}: deterministic={existing.raw_text!r} ai={text!r}",
                )
                merged[item.field] = _force_conflict_uncertain(existing, item, text)
                updated.append(item.field)
                outcomes[item.field] = "conflict"
                continue
            outcomes[item.field] = "kept_ocr"
            continue

        if existing.status not in {
            ExtractionStatus.UNCERTAIN,
            ExtractionStatus.NOT_FOUND,
        }:
            outcomes[item.field] = "skipped_status"
            continue

        if (
            existing.raw_text
            and existing.status == ExtractionStatus.UNCERTAIN
            and _material_conflict(existing, text, item.field)
            and not _mutually_reinforcing(existing, text, item.field)
        ):
            conflicts.append(
                f"{item.field}: deterministic={existing.raw_text!r} ai={text!r}",
            )
            merged[item.field] = _force_conflict_uncertain(existing, item, text)
            updated.append(item.field)
            outcomes[item.field] = "conflict"
            continue

        merged[item.field] = _apply_ai_fill(existing, item, text)
        updated.append(item.field)
        outcomes[item.field] = "filled"

    return merged, updated, conflicts, outcomes


def _force_conflict_uncertain(
    existing: ExtractedField,
    item: AiFieldEvidence,
    text: str,
) -> ExtractedField:
    hints = dict(existing.ai_fallback_hints)
    hints["ai_conflict"] = {
        "deterministic": existing.raw_text,
        "ai_candidate": text,
        "confidence": item.confidence.value,
    }
    hints["reason_code_hint"] = "CONFLICTING_EVIDENCE"
    return existing.model_copy(
        update={
            "status": ExtractionStatus.UNCERTAIN,
            "candidates": list(
                dict.fromkeys(
                    [*(existing.candidates or []), existing.raw_text or "", text],
                ),
            ),
            "explanation": (
                "CONFLICTING_EVIDENCE: OCR and AI evidence conflict for this field; "
                "human review required."
            ),
            "extraction_method": ExtractionMethod.COMBINED,
            "ai_fallback_hints": hints,
        },
    )


def _apply_supplement(
    existing: ExtractedField,
    item: AiFieldEvidence,
    text: str,
) -> ExtractedField:
    """Supplement FOUND OCR with mutually consistent AI detail (e.g. proof + ABV)."""
    numeric = existing.normalized_numeric
    unit = existing.normalized_unit
    normalized = existing.normalized_value or text
    raw = existing.raw_text or text

    if item.field == "alcohol_content":
        parsed = parse_alcohol_content(text)
        if parsed and parsed.abv_percent is not None:
            numeric = parsed.abv_percent
            unit = "%"
            normalized = alcohol_normalized_display(parsed)
            # Prefer AI span that includes ABV when OCR was proof-only.
            if parsed.source in {"abv", "both"}:
                raw = parsed.abv_span or text
                if parsed.proof_span and parsed.source == "both":
                    raw = text
    elif item.field == "net_contents":
        parsed = parse_net_contents(text)
        if parsed:
            numeric = parsed.value
            unit = parsed.unit
            normalized = f"{parsed.value:g} {parsed.unit}"
    elif item.field in {"brand_name", "class_type"}:
        from app.normalization.comparison import prefer_agreeing_text

        preferred = prefer_agreeing_text(existing.normalized_value or existing.raw_text, text)
        normalized = preferred or text
        raw = prefer_agreeing_text(existing.raw_text, text) or text
    elif item.field == "government_warning":
        normalized = "GOVERNMENT WARNING"
        raw = text

    hints = dict(existing.ai_fallback_hints)
    hints["ai_evidence"] = item.model_dump()
    hints["deterministic_raw_text"] = existing.raw_text
    hints["reconciliation"] = "mutually_reinforcing_supplement"
    # Mutually reinforcing evidence must not demote an existing FOUND result.
    return existing.model_copy(
        update={
            "status": ExtractionStatus.FOUND,
            "raw_text": raw,
            "normalized_value": normalized,
            "normalized_numeric": numeric,
            "normalized_unit": unit,
            "candidates": list(
                dict.fromkeys(
                    [*(existing.candidates or []), existing.raw_text or "", text],
                ),
            ),
            "extraction_method": ExtractionMethod.COMBINED,
            "explanation": (
                f"OCR and AI evidence agree; AI supplemented missing detail "
                f"({item.confidence.value})."
            ),
            "ai_fallback_hints": hints,
        },
    )


def _apply_ai_fill(
    existing: ExtractedField,
    item: AiFieldEvidence,
    text: str,
) -> ExtractedField:
    reinforcing = bool(
        (existing.raw_text or existing.normalized_value)
        and _mutually_reinforcing(existing, text, item.field),
    )
    # HIGH always promotes when validated. MEDIUM may promote only when an
    # independent OCR candidate already agrees after normalization.
    if item.confidence == AiEvidenceConfidence.HIGH:
        new_status = ExtractionStatus.FOUND
    elif reinforcing and item.confidence == AiEvidenceConfidence.MEDIUM:
        new_status = ExtractionStatus.FOUND
    else:
        new_status = ExtractionStatus.UNCERTAIN
    numeric = existing.normalized_numeric
    unit = existing.normalized_unit
    normalized = text
    raw = text
    if item.field == "alcohol_content":
        parsed = parse_alcohol_content(text)
        if parsed and parsed.abv_percent is not None:
            numeric = parsed.abv_percent
            unit = "%"
            normalized = alcohol_normalized_display(parsed)
    elif item.field == "net_contents":
        parsed = parse_net_contents(text)
        if parsed:
            numeric = parsed.value
            unit = parsed.unit
            normalized = f"{parsed.value:g} {parsed.unit}"
    elif item.field in {"brand_name", "class_type"}:
        from app.normalization.comparison import prefer_agreeing_text

        # Prefer complete AI recovery when it elaborates truncated OCR.
        preferred = prefer_agreeing_text(
            existing.normalized_value or existing.raw_text,
            text,
        )
        normalized = preferred or text
        raw = prefer_agreeing_text(existing.raw_text, text) or text
    elif item.field == "government_warning":
        normalized = "GOVERNMENT WARNING"

    hints = dict(existing.ai_fallback_hints)
    hints["ai_evidence"] = item.model_dump()
    hints["deterministic_raw_text"] = existing.raw_text
    hints["reconciliation"] = (
        "mutually_reinforcing_fill" if reinforcing else "ai_fill"
    )
    explanation = (
        f"Independent OCR and AI evidence agree after normalization "
        f"({item.confidence.value})."
        if reinforcing
        else (
            f"AI-assisted evidence recovery ({item.confidence.value}): "
            f"{item.evidence_description or 'vision recovery'}."
        )
    )
    return existing.model_copy(
        update={
            "status": new_status,
            "raw_text": raw,
            "normalized_value": normalized,
            "normalized_numeric": numeric,
            "normalized_unit": unit,
            "candidates": list(
                dict.fromkeys(
                    [
                        *(existing.candidates or []),
                        existing.raw_text or "",
                        text,
                    ],
                ),
            ),
            "extraction_method": ExtractionMethod.COMBINED,
            "explanation": explanation,
            "ai_fallback_hints": hints,
        },
    )


def _mutually_reinforcing(existing: ExtractedField, ai_text: str, field: str) -> bool:
    """True when AI elaborates OCR without contradicting it."""
    ocr = (existing.raw_text or existing.normalized_value or "").strip()
    if not ocr or not ai_text:
        return False

    if field == "alcohol_content":
        left = parse_alcohol_content(ocr)
        right = parse_alcohol_content(ai_text)
        if not right or right.abv_percent is None:
            return False
        if left is None:
            return False
        # Proof-only OCR + AI ABV that matches engineering transform.
        if left.source == "proof" and left.proof is not None and right.source in {"abv", "both"}:
            if right.proof is not None and abs(right.proof - left.proof) > 0.6:
                return False
            expected = left.proof / 2.0
            return abs(right.abv_percent - expected) <= 0.6
        if left.abv_percent is not None and right.abv_percent is not None:
            return abs(left.abv_percent - right.abv_percent) <= 0.5
        return False

    if field == "net_contents":
        left = parse_net_contents(ocr) or (
            parse_net_contents(existing.normalized_value or "")
        )
        right = parse_net_contents(ai_text)
        if left and right:
            left_ml = left.value * (1000.0 if left.unit == "L" else 1.0)
            right_ml = right.value * (1000.0 if right.unit == "L" else 1.0)
            return abs(left_ml - right_ml) <= 0.5
        return False

    from app.normalization.comparison import text_candidates_agree

    return text_candidates_agree(ocr, ai_text)


def _material_conflict(existing: ExtractedField, ai_text: str, field: str) -> bool:
    if _mutually_reinforcing(existing, ai_text, field):
        return False
    if field == "alcohol_content":
        left = parse_alcohol_content(existing.raw_text or existing.normalized_value or "")
        right = parse_alcohol_content(ai_text)
        if left and right and left.abv_percent is not None and right.abv_percent is not None:
            return abs(left.abv_percent - right.abv_percent) > 0.5
        # Proof vs unrelated text without parseable agreement.
        if left and right:
            return False
        return False
    if field == "net_contents":
        left = parse_net_contents(existing.normalized_value or existing.raw_text or "")
        right = parse_net_contents(ai_text)
        if left and right:
            left_ml = left.value * (1000.0 if left.unit == "L" else 1.0)
            right_ml = right.value * (1000.0 if right.unit == "L" else 1.0)
            return abs(left_ml - right_ml) > 0.5
        return False
    from app.normalization.comparison import text_candidates_agree

    a = (comparison_normalize(existing.raw_text or existing.normalized_value) or "")
    b = (comparison_normalize(ai_text) or "")
    if not a or not b:
        return False
    if text_candidates_agree(
        existing.raw_text or existing.normalized_value or "",
        ai_text,
    ):
        return False
    return True
