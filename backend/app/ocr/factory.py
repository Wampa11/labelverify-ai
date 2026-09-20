"""
OCR provider factory.

Architectural responsibility: construct providers by name without coupling callers
to engine SDKs.
"""

from __future__ import annotations

from app.ocr.base import OcrProvider
from app.ocr.easyocr_provider import EasyOcrProvider
from app.ocr.paddle_provider import PaddleOcrProvider
from app.ocr.rapidocr_provider import RapidOcrProvider
from app.ocr.stub import StubOcrProvider
from app.ocr.tesseract_provider import TesseractOcrProvider


def create_ocr_provider(name: str) -> OcrProvider:
    """Return an OCR provider instance for the given stable name."""
    normalized = name.strip().lower()
    if normalized in {"stub", "none"}:
        return StubOcrProvider()
    if normalized == "tesseract":
        return TesseractOcrProvider()
    if normalized in {"paddle", "paddleocr"}:
        return PaddleOcrProvider()
    if normalized == "easyocr":
        return EasyOcrProvider()
    if normalized == "rapidocr":
        return RapidOcrProvider()
    raise ValueError(f"Unknown OCR provider: {name!r}")


def list_available_providers() -> list[str]:
    """Probe installed engines and return those that report available."""
    candidates = ["tesseract", "paddleocr", "easyocr", "rapidocr"]
    available: list[str] = []
    for name in candidates:
        provider = create_ocr_provider(name)
        if provider.is_available():
            available.append(provider.name)
    return available
