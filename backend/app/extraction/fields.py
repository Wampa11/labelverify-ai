"""
Field extractor facade for structured label fields.

Architectural responsibility: map OCR evidence to ExtractedField results.
Phase 4 delegates to per-field extractors; does not produce regulatory decisions.
"""

from app.extraction.pipeline import extract_all_fields
from app.models.extraction import ExtractedField
from app.ocr.base import OcrResult


class FieldExtractor:
    """Extracts structured fields from OCR output via per-field extractors."""

    def extract(self, ocr_result: OcrResult) -> dict[str, ExtractedField]:
        """Map OCR evidence to named fields (FOUND / UNCERTAIN / NOT_FOUND)."""
        return extract_all_fields(ocr_result)
