"""
OCR package: pluggable text detection for label images.

Architectural responsibility: OCR port/adapters and evaluation harness —
no regulatory rules or OpenAI calls.
"""

from app.ocr.base import BoundingBox, OcrProvider, OcrResult, OcrWord
from app.ocr.factory import create_ocr_provider, list_available_providers

__all__ = [
    "BoundingBox",
    "OcrProvider",
    "OcrResult",
    "OcrWord",
    "create_ocr_provider",
    "list_available_providers",
]
