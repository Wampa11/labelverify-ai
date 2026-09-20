"""
OCR provider interface (port) and shared result contract.

Architectural responsibility: define the contract so business logic does not depend
on a specific OCR library. Confidence is never invented when an engine omits it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Axis-aligned box in image pixel coordinates (origin top-left)."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def as_dict(self) -> dict[str, float]:
        """Serialize for JSON-friendly word metadata."""
        return {
            "x_min": self.x_min,
            "y_min": self.y_min,
            "x_max": self.x_max,
            "y_max": self.y_max,
        }


class OcrWord(BaseModel):
    """A single OCR word or token with optional geometry and engine confidence."""

    text: str
    confidence: float | None = Field(
        default=None,
        description="Provider-measured confidence in [0, 1] when available; never invent",
        ge=0.0,
        le=1.0,
    )
    bounding_box: dict[str, Any] | None = None
    polygon: list[list[float]] | None = Field(
        default=None,
        description="Optional polygon as list of [x, y] points when the engine provides it",
    )


class OcrResult(BaseModel):
    """Normalized OCR output consumed by extraction and evaluation."""

    full_text: str
    words: list[OcrWord] = Field(default_factory=list)
    provider_name: str
    image_width_px: int | None = None
    image_height_px: int | None = None
    processing_time_ms: float | None = Field(
        default=None,
        description="Wall-clock OCR engine time only (excludes preprocessing)",
    )
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    preprocessing_profile: str | None = Field(
        default=None,
        description="Name of preprocessing profile applied before OCR, if known",
    )
    confidence_scale_notes: str | None = Field(
        default=None,
        description="How this engine's confidence should be interpreted",
    )
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def has_text(self) -> bool:
        """True when any non-whitespace text was recovered."""
        return bool(self.full_text.strip()) or any(w.text.strip() for w in self.words)

    @property
    def has_bounding_boxes(self) -> bool:
        """True when at least one word includes geometry."""
        return any(w.bounding_box or w.polygon for w in self.words)


class OcrProvider(ABC):
    """Abstract OCR engine. Concrete adapters live alongside this module."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider identifier (e.g. stub, tesseract, paddleocr)."""

    @abstractmethod
    def extract_text(self, image_bytes: bytes) -> OcrResult:
        """
        Run OCR on image bytes and return structured text evidence.

        Implementations must not invent confidence values. Failures should raise
        OcrProviderError (or return an empty result with explicit errors — prefer raise).
        """

    def is_available(self) -> bool:
        """Return True when the engine and its runtime dependencies are usable."""
        return True
