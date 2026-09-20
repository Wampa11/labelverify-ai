"""
Stub OCR provider used when no engine is configured.

Architectural responsibility: refuse to invent detections; fail explicitly.
"""

from app.ocr.base import OcrProvider, OcrResult
from app.ocr.errors import OcrProviderError


class StubOcrProvider(OcrProvider):
    """Placeholder OCR that refuses to invent detections."""

    @property
    def name(self) -> str:
        return "stub"

    def is_available(self) -> bool:
        return False

    def extract_text(self, image_bytes: bytes) -> OcrResult:
        """Raise until a real OCR implementation is selected and wired."""
        if not image_bytes:
            raise ValueError("image_bytes must not be empty")
        raise OcrProviderError(
            "OCR stub cannot extract text. Select tesseract or paddleocr after evaluation.",
            provider_name=self.name,
            code="ocr_not_configured",
        )
