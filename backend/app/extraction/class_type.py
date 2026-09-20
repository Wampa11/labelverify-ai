"""
Class/type extractor assisted by known beverage terminology.

Architectural responsibility: locate class/type candidates — not final classification.
"""

from __future__ import annotations

from app.extraction.ocr_support import lines_from_ocr, regions_for_snippet
from app.extraction.terminology import CLASS_TYPE_KEYWORDS, CLASS_TYPE_PHRASES
from app.models.extraction import (
    ExtractedField,
    ExtractionMethod,
    ExtractionStatus,
)
from app.ocr.base import OcrResult


def extract_class_type(ocr: OcrResult) -> ExtractedField:
    """Extract class/type using phrase/keyword matches; UNCERTAIN if several match."""
    field_name = "class_type"
    lines = lines_from_ocr(ocr)
    full = (ocr.full_text or "").lower()

    phrase_hits: list[str] = []
    for phrase in CLASS_TYPE_PHRASES:
        if phrase in full:
            # Prefer original-casing line containing the phrase.
            for line in lines:
                if phrase in line.lower():
                    phrase_hits.append(line)
                    break
            else:
                phrase_hits.append(phrase)

    # Deduplicate while preserving order.
    unique: list[str] = []
    for hit in phrase_hits:
        if hit not in unique:
            unique.append(hit)

    if not unique:
        keyword_hits = [
            line
            for line in lines
            if any(keyword in line.lower() for keyword in CLASS_TYPE_KEYWORDS)
        ]
        if not keyword_hits:
            return ExtractedField(
                field_name=field_name,
                status=ExtractionStatus.NOT_FOUND,
                explanation="No class/type terminology matches were found in OCR text.",
                extraction_method=ExtractionMethod.NOT_EXTRACTED,
                ai_fallback_hints={"reason": "class_type_missing"},
            )
        if len(keyword_hits) > 1:
            return ExtractedField(
                field_name=field_name,
                status=ExtractionStatus.UNCERTAIN,
                raw_text=keyword_hits[0],
                normalized_value=keyword_hits[0],
                candidates=keyword_hits[:5],
                ocr_regions=regions_for_snippet(ocr, keyword_hits[0]),
                extraction_method=ExtractionMethod.TERMINOLOGY_MATCH,
                explanation=(
                    "Multiple keyword-based class/type candidates; "
                    "not arbitrarily choosing one."
                ),
                ai_fallback_hints={
                    "reason": "class_type_ambiguous",
                    "candidates": keyword_hits[:5],
                },
            )
        return ExtractedField(
            field_name=field_name,
            status=ExtractionStatus.UNCERTAIN,
            raw_text=keyword_hits[0],
            normalized_value=keyword_hits[0],
            candidates=keyword_hits,
            ocr_regions=regions_for_snippet(ocr, keyword_hits[0]),
            extraction_method=ExtractionMethod.TERMINOLOGY_MATCH,
            explanation="Single weak keyword match for class/type; marked uncertain.",
        )

    if len(unique) > 1:
        return ExtractedField(
            field_name=field_name,
            status=ExtractionStatus.UNCERTAIN,
            raw_text=unique[0],
            normalized_value=unique[0],
            candidates=unique[:5],
            ocr_regions=regions_for_snippet(ocr, unique[0]),
            extraction_method=ExtractionMethod.TERMINOLOGY_MATCH,
            explanation="Multiple class/type phrase matches; preserving ambiguity.",
            ai_fallback_hints={"reason": "class_type_ambiguous", "candidates": unique[:5]},
        )

    candidate = unique[0]
    # Truncated / ellipsis OCR for class/type is recoverable but not certain.
    if _looks_partial_class(candidate):
        return ExtractedField(
            field_name=field_name,
            status=ExtractionStatus.UNCERTAIN,
            raw_text=candidate,
            normalized_value=candidate,
            candidates=unique,
            ocr_regions=regions_for_snippet(ocr, candidate),
            extraction_method=ExtractionMethod.TERMINOLOGY_MATCH,
            explanation="Class/type evidence appears partial or truncated.",
            ai_fallback_hints={"reason": "class_type_partial", "candidates": unique},
        )

    return ExtractedField(
        field_name=field_name,
        status=ExtractionStatus.FOUND,
        raw_text=candidate,
        normalized_value=candidate,
        candidates=unique,
        ocr_regions=regions_for_snippet(ocr, candidate),
        extraction_method=ExtractionMethod.TERMINOLOGY_MATCH,
        explanation=f"Class/type was recovered as {candidate}.",
    )


def _looks_partial_class(text: str) -> bool:
    stripped = text.strip()
    if stripped.endswith(("...", "…", " Whis", " WHIS", " Bourb")):
        return True
    if "..." in stripped or "…" in stripped:
        return True
    # Very short keyword-only lines without a full phrase.
    lowered = stripped.lower()
    if any(phrase in lowered for phrase in CLASS_TYPE_PHRASES):
        return False
    return len(stripped.split()) <= 2

