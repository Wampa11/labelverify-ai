"""
OCR-specific exceptions.

Architectural responsibility: make OCR failures observable — never silent success.
"""

from app.core.exceptions import LabelVerifyError


class OcrProviderError(LabelVerifyError):
    """Raised when an OCR provider cannot complete extraction."""

    def __init__(
        self,
        message: str,
        *,
        provider_name: str,
        code: str = "ocr_failed",
        details: str | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.provider_name = provider_name
        self.code = code
