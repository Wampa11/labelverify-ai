"""
Brand extraction diagnostics (non-mutating).

Architectural responsibility: explain candidate scoring and selection without
changing FOUND/UNCERTAIN/NOT_FOUND outcomes used by production extractors.
"""

from __future__ import annotations

from typing import Any

from app.extraction import brand_name as brand
from app.extraction.ocr_support import bbox_height, bbox_top, lines_from_ocr
from app.normalization.field_parsers import parse_alcohol_content, parse_net_contents
from app.ocr.base import OcrResult


def ocr_words_as_dicts(ocr: OcrResult) -> list[dict[str, Any]]:
    """Serialize OCR words for diagnostics (no image bytes)."""
    rows: list[dict[str, Any]] = []
    for word in ocr.words:
        rows.append(
            {
                "text": word.text,
                "confidence": word.confidence,
                "bounding_box": word.bounding_box,
            },
        )
    return rows


def brand_region_words(ocr: OcrResult, line: str | None) -> list[dict[str, Any]]:
    """Words overlapping a candidate line (same matching as the extractor)."""
    if not line:
        return []
    words = brand._words_for_line(ocr, line)
    return [
        {
            "text": w.text,
            "confidence": w.confidence,
            "bounding_box": w.bounding_box,
        }
        for w in words
    ]


def score_candidates_detailed(ocr: OcrResult, lines: list[str]) -> list[dict[str, Any]]:
    """
    Mirror brand_name._score_candidates with explicit bonus/penalty components.

    Scores must match production scoring (same formulas).
    """
    image_height = float(ocr.image_height_px or 1)
    detailed: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        components: dict[str, float] = {}
        bonuses: list[str] = []
        penalties: list[str] = []
        words = brand._words_for_line(ocr, line)
        if words:
            avg_h = sum(bbox_height(w) for w in words) / len(words)
            avg_top = sum(bbox_top(w) for w in words) / len(words)
            size_term = avg_h * 2.0
            position_term = max(0.0, 1.0 - (avg_top / image_height)) * 40.0
            components["size_height"] = size_term
            components["upper_position"] = position_term
            score = size_term + position_term
            if len(words) >= 2:
                ordered = sorted(words, key=lambda w: brand._bbox_left(w))
                gaps = []
                for left, right in zip(ordered, ordered[1:], strict=False):
                    gap = brand._bbox_left(right) - (
                        brand._bbox_left(left) + brand._bbox_width(left)
                    )
                    gaps.append(gap)
                if gaps and all(g < avg_h * 1.8 for g in gaps):
                    score += 10.0
                    components["continuity"] = 10.0
                    bonuses.append("horizontal_continuity_+10")
        else:
            score = 30.0 - index
            components["line_index_fallback"] = score

        token_count = len(line.split())
        if token_count >= 2:
            score += 8.0
            components["multi_word"] = 8.0
            bonuses.append("multi_word_+8")
        if line.isupper() and len(line) > 4:
            score += 5.0
            components["all_caps"] = 5.0
            bonuses.append("all_caps_+5")
        if brand._is_weak_standalone(line):
            score -= 28.0
            components["weak_standalone"] = -28.0
            penalties.append("weak_standalone_-28")
        if brand._OCR_ARTIFACT.search(line) or brand._LEADING_TRAILING_JUNK.search(
            line.strip(),
        ):
            score -= 20.0
            components["ocr_artifact"] = -20.0
            penalties.append("ocr_artifact_-20")

        detailed.append(
            {
                "line": line,
                "score": score,
                "components": components,
                "bonuses": bonuses,
                "penalties": penalties,
                "words": [
                    {
                        "text": w.text,
                        "confidence": w.confidence,
                        "bounding_box": w.bounding_box,
                    }
                    for w in words
                ],
            },
        )
    detailed.sort(key=lambda item: item["score"], reverse=True)
    return detailed


def diagnose_brand_from_ocr(
    ocr: OcrResult,
    *,
    source_pass: str,
) -> dict[str, Any]:
    """
    Full brand-stage diagnostic for one OCR result.

    Calls production ``extract_brand_name`` for the authoritative field outcome,
    then attaches candidate scoring detail (must not diverge from selection logic).
    """
    lines = lines_from_ocr(ocr)
    filtered = [
        line
        for line in lines
        if not brand._SKIP_LINE.search(line)
        and parse_alcohol_content(line) is None
        and parse_net_contents(line) is None
        and not brand._looks_like_class(line)
        and not brand._looks_like_warning_fragment(line)
        and 3 <= len(line) <= 60
    ]
    detailed = score_candidates_detailed(ocr, filtered)
    field = brand.extract_brand_name(ocr)

    selection_reason = "not_selected"
    if field.status.value == "NOT_FOUND":
        selection_reason = field.ai_fallback_hints.get("reason") or "no_candidates"
    elif field.ai_fallback_hints.get("reason") == "brand_ambiguous":
        selection_reason = "near_tied_or_suffix_conflict_uncertain"
    elif field.ai_fallback_hints.get("reason") == "brand_weak_standalone":
        selection_reason = "weak_standalone_uncertain"
    elif field.ai_fallback_hints.get("reason") == "brand_integrity":
        selection_reason = (
            "integrity_gate_uncertain:"
            + ",".join(field.ai_fallback_hints.get("integrity_issues") or [])
        )
    elif field.status.value == "FOUND":
        selection_reason = "top_score_unique_passed_integrity"

    return {
        "source_pass": source_pass,
        "ocr_full_text": ocr.full_text,
        "ocr_word_count": len(ocr.words),
        "ocr_image_size": {
            "width_px": ocr.image_width_px,
            "height_px": ocr.image_height_px,
        },
        "all_ocr_words": ocr_words_as_dicts(ocr),
        "lines": lines,
        "filtered_candidates": filtered,
        "scored_candidates": detailed,
        "winning_raw": field.raw_text,
        "winning_normalized": field.normalized_value,
        "extraction_status": field.status.value,
        "extraction_explanation": field.explanation,
        "selection_reason": selection_reason,
        "integrity_issues": field.ai_fallback_hints.get("integrity_issues"),
        "ai_fallback_hints": field.ai_fallback_hints,
        "winning_region_words": brand_region_words(ocr, field.raw_text),
        "field_snapshot": {
            "status": field.status.value,
            "raw_text": field.raw_text,
            "normalized_value": field.normalized_value,
            "candidates": field.candidates,
            "extraction_method": field.extraction_method.value,
        },
    }


def contains_visible_brand_tokens(ocr_text: str, expected_tokens: list[str]) -> dict[str, bool]:
    """Helper for scripts: which expected tokens appear in OCR (case-insensitive)."""
    lowered = (ocr_text or "").casefold()
    return {token: token.casefold() in lowered for token in expected_tokens}
