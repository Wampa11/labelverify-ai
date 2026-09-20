"""
Field extraction from OCR evidence.

Architectural responsibility:
map OCR/layout signals to named label fields — not regulatory PASS/FAIL.
"""

from app.extraction.fields import FieldExtractorfrom app.extraction.pipeline import FIELD_ORDER, extract_all_fields__all__ = ["FIELD_ORDER", "FieldExtractor", "extract_all_fields"]
