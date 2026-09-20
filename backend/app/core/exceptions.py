"""
Shared exceptions for the LabelVerify AI backend.

Architectural responsibility: explicit error types so failures are never silently swallowed.
"""


class LabelVerifyError(Exception):
    """Base error for LabelVerify AI domain failures."""

    def __init__(self, message: str, *, details: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ConfigurationError(LabelVerifyError):
    """Raised when required configuration is missing or invalid."""


class NotImplementedStageError(LabelVerifyError):
    """Raised when a pipeline stage is scaffolded but not yet implemented."""


class ImageValidationError(LabelVerifyError):
    """Raised when an uploaded image fails validation (format, size, corruption, etc.)."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "image_validation_failed",
        details: str | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.code = code
