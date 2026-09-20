"""
AI provider port for optional fallback assistance.

Architectural responsibility: keep verification services free of vendor-specific AI SDKs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum

from pydantic import BaseModel, Field

from app.ai.evidence import AiEvidenceBatchResult, AiEvidencePackage
from app.ai.package import PreparedAiImage


class AiAvailability(StrEnum):
    """Whether the AI provider can be used for a call."""

    AVAILABLE = "available"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"


class AiAssistRequest(BaseModel):
    """Legacy structured text request (kept for compatibility)."""

    task: str
    context: dict[str, str] = Field(default_factory=dict)


class AiAssistResponse(BaseModel):
    """Structured AI response with observable availability/degradation."""

    availability: AiAvailability
    content: str | None = None
    explanation: str
    provider_name: str


class AiProvider(ABC):
    """Abstract optional AI capability used only after deterministic stages."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier."""

    @abstractmethod
    def availability(self) -> AiAvailability:
        """Report whether AI can be invoked without inventing answers."""

    @abstractmethod
    def assist(self, request: AiAssistRequest) -> AiAssistResponse:
        """
        Attempt text assistance for an ambiguous case.

        Must not be called from rules or OCR modules directly —
        orchestration belongs in services.
        """

    def recover_label_evidence(
        self,
        package: AiEvidencePackage,
        image: PreparedAiImage,
    ) -> AiEvidenceBatchResult:
        """
        Recover structured label-field evidence from an image.

        Default: not implemented / unavailable. OpenAI adapter overrides.
        Must never return regulatory PASS/REVIEW/FAIL.
        """
        return AiEvidenceBatchResult(
            availability=self.availability().value,
            provider_name=self.name,
            fields=[],
            explanation=(
                f"Vision evidence recovery is not implemented for provider {self.name!r}."
            ),
            called=False,
        )
