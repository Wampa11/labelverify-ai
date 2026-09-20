"""
Alcohol content (ABV / proof) field extractor.

Architectural responsibility: isolate % Alc./Vol. and proof spans from OCR lines.
Proof alone never substitutes for a mandatory ABV statement at the rules layer.
"""

from __future__ import annotations

from app.extraction.ocr_support import lines_from_ocr, regions_for_snippet
from app.models.extraction import (
    ExtractedField,
    ExtractionMethod,
    ExtractionStatus,
)
from app.normalization.field_parsers import alcohol_normalized_display, parse_alcohol_content
from app.ocr.base import OcrResult


def extract_alcohol_content(ocr: OcrResult) -> ExtractedField:
    """Extract ABV/proof from OCR; prefer explicit % Alc./Vol. over proof-only."""
    field_name = "alcohol_content"
    candidates: list[str] = []
    best = None
    best_line: str | None = None

    for line in lines_from_ocr(ocr):
        parsed = parse_alcohol_content(line)
        if parsed is None:
            continue
        candidates.append(line)
        if best is None:
            best = parsed
            best_line = line
            continue
        # Prefer ABV / both over proof-only; prefer both when available.
        rank = {"proof": 0, "abv": 1, "both": 2}
        if rank.get(parsed.source, 0) > rank.get(best.source, 0):
            best = parsed
            best_line = line
        elif parsed.source == best.source == "both":
            best = parsed
            best_line = line

    if best is None:
        parsed = parse_alcohol_content(ocr.full_text or "")
        if parsed is not None:
            best = parsed
            best_line = parsed.abv_span or parsed.proof_span or parsed.raw_text
            candidates.append(best_line)

    if best is None or best.abv_percent is None:
        return ExtractedField(
            field_name=field_name,
            status=ExtractionStatus.NOT_FOUND,
            explanation="Alcohol content could not be reliably extracted.",
            extraction_method=ExtractionMethod.NOT_EXTRACTED,
            ai_fallback_hints={
                "reason": "abv_pattern_missing",
                "ocr_preview": (ocr.full_text or "")[:400],
            },
        )

    # Evidence text for technical details: prefer the line; fall back to spans.
    if best.source == "both" and best_line:
        raw = best_line
    elif best.source == "abv":
        raw = best.abv_span or best_line or best.raw_text
    else:
        raw = best.proof_span or best_line or best.raw_text

    regions = regions_for_snippet(ocr, raw)
    low_conf = any(r.confidence is not None and r.confidence < 0.45 for r in regions)

    # Proof-only is recoverable evidence but not a complete mandatory ABV statement.
    if best.source == "proof":
        status = ExtractionStatus.UNCERTAIN if low_conf else ExtractionStatus.FOUND
        explanation = (
            "Proof was recovered without a clear percentage alcohol-by-volume statement."
        )
    elif low_conf:
        status = ExtractionStatus.UNCERTAIN
        explanation = "Alcohol content could not be reliably extracted."
    else:
        status = ExtractionStatus.FOUND
        explanation = f"Alcohol content was recovered as {alcohol_normalized_display(best)}."

    return ExtractedField(
        field_name=field_name,
        status=status,
        raw_text=raw,
        normalized_value=alcohol_normalized_display(best),
        normalized_numeric=best.abv_percent,
        normalized_unit="%",
        candidates=candidates,
        ocr_regions=regions,
        extraction_method=ExtractionMethod.REGEX,
        explanation=explanation,
        ai_fallback_hints={
            "source": best.source,
            "abv_span": best.abv_span,
            "proof_span": best.proof_span,
        },
    )
