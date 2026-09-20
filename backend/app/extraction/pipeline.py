"""
Coordinate extraction of all structured label fields from one OCR result.

Architectural responsibility: run field extractors and assemble a field map.
"""

from __future__ import annotations

from app.extraction.alcohol_content import extract_alcohol_content
from app.extraction.brand_name import extract_brand_name
from app.extraction.class_type import extract_class_type
from app.extraction.government_warning import extract_government_warning
from app.extraction.net_contents import extract_net_contents
from app.models.extraction import ExtractedField
from app.ocr.base import OcrResult

FIELD_ORDER = (
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "government_warning",
)


def extract_all_fields(ocr: OcrResult) -> dict[str, ExtractedField]:
    """Run all Phase 4 field extractors against one OCR result."""
    fields = {
        "brand_name": extract_brand_name(ocr),
        "class_type": extract_class_type(ocr),
        "alcohol_content": extract_alcohol_content(ocr),
        "net_contents": extract_net_contents(ocr),
        "government_warning": extract_government_warning(ocr),
    }
    return fields
