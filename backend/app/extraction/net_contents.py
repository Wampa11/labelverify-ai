"""
Net contents field extractor.

Architectural responsibility: isolate quantity+unit from OCR; keep raw line evidence
separate from the normalized volume display. Does not invent missing digits.
"""

from __future__ import annotations

from app.extraction.ocr_support import lines_from_ocr, regions_for_snippet
from app.models.extraction import (
    ExtractedField,
    ExtractionMethod,
    ExtractionStatus,
)
from app.normalization.field_parsers import (
    net_contents_evidence_is_reliable,
    parse_net_contents,
)
from app.ocr.base import OcrResult


def extract_net_contents(ocr: OcrResult) -> ExtractedField:
    """Extract net contents value/unit (mL or L) from recognized volume patterns."""
    field_name = "net_contents"
    candidates: list[str] = []
    best = None
    best_line: str | None = None
    reliable = False

    for line in lines_from_ocr(ocr):
        parsed = parse_net_contents(line)
        if parsed is None:
            continue
        candidates.append(line)
        line_reliable = net_contents_evidence_is_reliable(line, parsed)
        # Prefer a reliable match over an earlier noisy one.
        if best is None or (line_reliable and not reliable):
            best = parsed
            best_line = line
            reliable = line_reliable
            if line_reliable:
                break

    if best is None:
        parsed = parse_net_contents(ocr.full_text or "")
        if parsed is not None:
            best = parsed
            best_line = parsed.match_span or parsed.raw_text
            candidates.append(best_line)
            reliable = net_contents_evidence_is_reliable(ocr.full_text or "", parsed)

    if best is None:
        return ExtractedField(
            field_name=field_name,
            status=ExtractionStatus.NOT_FOUND,
            explanation="No recognizable net contents quantity/unit was found.",
            extraction_method=ExtractionMethod.NOT_EXTRACTED,
            ai_fallback_hints={"reason": "net_contents_pattern_missing"},
        )

    regions = regions_for_snippet(ocr, best_line or best.raw_text)
    low_conf = any(r.confidence is not None and r.confidence < 0.45 for r in regions)
    status = ExtractionStatus.FOUND
    if not reliable or low_conf:
        status = ExtractionStatus.UNCERTAIN

    normalized = f"{best.value:g} {best.unit}"
    if status == ExtractionStatus.FOUND:
        explanation = f"Net contents were recovered as {normalized}."
    else:
        explanation = (
            f"Net contents pattern matched {normalized}, but surrounding OCR evidence "
            f"is noisy or low-confidence; treated as uncertain."
        )

    return ExtractedField(
        field_name=field_name,
        status=status,
        raw_text=best_line or best.match_span or best.raw_text,
        normalized_value=normalized,
        normalized_numeric=best.value,
        normalized_unit=best.unit,
        candidates=candidates,
        ocr_regions=regions,
        extraction_method=ExtractionMethod.REGEX,
        explanation=explanation,
        ai_fallback_hints={
            "reason": "net_contents_noisy_context" if not reliable else "",
            "match_span": best.match_span,
            "evidence_reliable": reliable,
        }
        if not reliable
        else {"match_span": best.match_span, "evidence_reliable": True},
    )
