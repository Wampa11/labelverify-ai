"""
Objective OCR evaluation metrics.

Architectural responsibility: CER and compliance-field recovery scoring without
regulatory PASS/FAIL decisions.
"""

from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

from app.ocr.evaluate.ground_truth import ComplianceFieldTruth, FixtureGroundTruth


def normalize_for_compare(text: str) -> str:
    """Lowercase, collapse whitespace, strip most punctuation for field recovery."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.lower()
    text = re.sub(r"[^\w\s.%/]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def character_error_rate(reference: str, hypothesis: str) -> float:
    """
    Character error rate = edit_distance / max(1, len(reference)).

    Uses Unicode code points after light whitespace normalization.
    """
    ref = re.sub(r"\s+", " ", (reference or "").strip())
    hyp = re.sub(r"\s+", " ", (hypothesis or "").strip())
    if not ref and not hyp:
        return 0.0
    if not ref:
        return 1.0
    distance = _levenshtein(ref, hyp)
    return distance / max(1, len(ref))


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (0 if ca == cb else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def field_recovered(
    ocr_text: str,
    truth: ComplianceFieldTruth,
    *,
    exact_threshold: int = 85,
    semantic_threshold: int = 90,
) -> bool:
    """
    Return True when OCR text sufficiently recovers the field.

    Prefers semantic_value when present (e.g. ABV 45), else fuzzy exact_text match.
    Thresholds are evaluation heuristics, not regulatory certainty.
    """
    haystack = normalize_for_compare(ocr_text)
    if not haystack:
        return False

    if truth.semantic_value:
        needle = normalize_for_compare(truth.semantic_value)
        if needle and needle in haystack:
            return True
        if needle and fuzz.partial_ratio(needle, haystack) >= semantic_threshold:
            return True

    exact = normalize_for_compare(truth.exact_text)
    if exact and exact in haystack:
        return True
    if exact and fuzz.partial_ratio(exact, haystack) >= exact_threshold:
        return True
    return False


def score_compliance_fields(
    ocr_text: str,
    ground_truth: FixtureGroundTruth,
) -> dict[str, bool]:
    """Score each compliance-relevant field independently."""
    return {
        "brand_name": field_recovered(ocr_text, ground_truth.brand_name),
        "class_type": field_recovered(ocr_text, ground_truth.class_type),
        "alcohol_content_abv": field_recovered(
            ocr_text,
            ground_truth.alcohol_content_abv,
        ),
        "net_contents": field_recovered(ocr_text, ground_truth.net_contents),
        "government_health_warning": field_recovered(
            ocr_text,
            ground_truth.government_health_warning,
            exact_threshold=75,
        ),
    }


def brand_exact_recovered(ocr_text: str, truth: ComplianceFieldTruth) -> bool:
    """True when exact brand text appears in OCR after light whitespace normalize."""
    hay = re.sub(r"\s+", " ", (ocr_text or "").strip()).casefold()
    needle = re.sub(r"\s+", " ", (truth.exact_text or "").strip()).casefold()
    return bool(needle) and needle in hay


def brand_normalized_recovered(ocr_text: str, truth: ComplianceFieldTruth) -> bool:
    """True when brand recovers under evaluation field_recovered heuristics."""
    return field_recovered(ocr_text, truth)


def reference_full_text(ground_truth: FixtureGroundTruth) -> str:
    """Concatenate exact field texts for CER against full OCR output."""
    parts = [
        ground_truth.brand_name.exact_text,
        ground_truth.class_type.exact_text,
        ground_truth.alcohol_content_abv.exact_text,
        ground_truth.net_contents.exact_text,
        ground_truth.government_health_warning.exact_text,
    ]
    return "\n".join(parts)

