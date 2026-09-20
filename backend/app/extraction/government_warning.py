"""
Government health warning detection/extraction (not regulatory compliance).

Architectural responsibility: locate GOVERNMENT WARNING text and associated body.
Does not enforce statutory wording, capitalization, bold, size, or placement.
"""

from __future__ import annotations

import re

from app.extraction.ocr_support import lines_from_ocr, regions_for_snippet
from app.models.extraction import (
    ExtractedField,
    ExtractionMethod,
    ExtractionStatus,
)
from app.ocr.base import OcrResult

_WARNING_HEADER = re.compile(r"government\s+warning", re.IGNORECASE)


def extract_government_warning(ocr: OcrResult) -> ExtractedField:
    """Detect warning header and collect following OCR lines as warning body."""
    field_name = "government_warning"
    lines = lines_from_ocr(ocr)
    header_index = None
    for index, line in enumerate(lines):
        if _WARNING_HEADER.search(line):
            header_index = index
            break

    if header_index is None:
        # Search full text for header even if line-broken oddly.
        if not _WARNING_HEADER.search(ocr.full_text or ""):
            return ExtractedField(
                field_name=field_name,
                status=ExtractionStatus.NOT_FOUND,
                explanation="No 'GOVERNMENT WARNING' header was detected in OCR text.",
                extraction_method=ExtractionMethod.NOT_EXTRACTED,
                ai_fallback_hints={"reason": "warning_header_missing"},
            )
        # Header in full text but not cleanly lined — uncertain partial.
        snippet = (ocr.full_text or "")[:500]
        return ExtractedField(
            field_name=field_name,
            status=ExtractionStatus.UNCERTAIN,
            raw_text=snippet,
            normalized_value="GOVERNMENT WARNING",
            ocr_regions=regions_for_snippet(ocr, "GOVERNMENT WARNING"),
            extraction_method=ExtractionMethod.REGEX,
            explanation=(
                "Warning header appears in OCR text but line structure is unclear; "
                "treated as partial/uncertain extraction."
            ),
            ai_fallback_hints={"reason": "warning_partial_structure"},
        )

    body_lines = lines[header_index:]
    raw = " ".join(body_lines).strip()
    regions = regions_for_snippet(ocr, raw[:200])
    # Heuristic completeness: surgeon general / pregnancy / machinery cues.
    lowered = raw.lower()
    cues = sum(
        1
        for cue in ("surgeon general", "pregnancy", "machinery", "health problems", "birth defects")
        if cue in lowered
    )
    if cues >= 2 and len(raw) > 80:
        status = ExtractionStatus.FOUND
        explanation = "Warning header and substantial associated text were recovered."
    elif cues >= 1 or len(raw) > 40:
        status = ExtractionStatus.UNCERTAIN
        explanation = (
            "Warning header found but associated text appears partial or incomplete."
        )
    else:
        status = ExtractionStatus.UNCERTAIN
        explanation = "Warning header found with little following text."

    return ExtractedField(
        field_name=field_name,
        status=status,
        raw_text=raw,
        normalized_value="GOVERNMENT WARNING",
        ocr_regions=regions,
        extraction_method=ExtractionMethod.COMBINED,
        explanation=explanation,
        ai_fallback_hints={"reason": "warning_for_ai"} if status != ExtractionStatus.FOUND else {},
    )
