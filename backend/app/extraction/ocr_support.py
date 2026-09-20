"""
Shared helpers for mapping OCR words into field evidence.

Architectural responsibility: OCR geometry utilities for extractors — not field rules.
"""

from __future__ import annotations

from app.models.extraction import OcrRegionRef
from app.ocr.base import OcrResult, OcrWord


def lines_from_ocr(ocr: OcrResult) -> list[str]:
    """Split OCR full_text into non-empty lines."""
    return [line.strip() for line in (ocr.full_text or "").splitlines() if line.strip()]


def words_overlapping_text(ocr: OcrResult, snippet: str) -> list[OcrWord]:
    """Return OCR words whose text appears in snippet (case-insensitive token match)."""
    if not snippet:
        return []
    tokens = {t.lower() for t in snippet.split() if t}
    matched: list[OcrWord] = []
    for word in ocr.words:
        if word.text.lower() in tokens:
            matched.append(word)
    return matched


def regions_for_snippet(ocr: OcrResult, snippet: str) -> list[OcrRegionRef]:
    """Build OcrRegionRef list for words supporting a snippet."""
    refs: list[OcrRegionRef] = []
    for word in words_overlapping_text(ocr, snippet):
        refs.append(
            OcrRegionRef(
                text=word.text,
                confidence=word.confidence,
                bounding_box=word.bounding_box,
                provider_name=ocr.provider_name,
                preprocessing_profile=ocr.preprocessing_profile,
            ),
        )
    if not refs and snippet:
        refs.append(
            OcrRegionRef(
                text=snippet,
                confidence=None,
                bounding_box=None,
                provider_name=ocr.provider_name,
                preprocessing_profile=ocr.preprocessing_profile,
            ),
        )
    return refs


def mean_confidence(regions: list[OcrRegionRef]) -> float | None:
    """Average engine confidence when present; never invent values."""
    values = [r.confidence for r in regions if r.confidence is not None]
    if not values:
        return None
    return sum(values) / len(values)


def bbox_height(word: OcrWord) -> float:
    """Height of word bounding box, or 0 when missing."""
    box = word.bounding_box or {}
    try:
        return float(box.get("y_max", 0)) - float(box.get("y_min", 0))
    except (TypeError, ValueError):
        return 0.0


def bbox_top(word: OcrWord) -> float:
    """Top of word bounding box, or a large number when missing."""
    box = word.bounding_box or {}
    try:
        return float(box.get("y_min", 1e9))
    except (TypeError, ValueError):
        return 1e9
