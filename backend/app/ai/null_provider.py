"""
Null/disabled AI provider for graceful operation without OpenAI.

Architectural responsibility: explicit no-op path when AI is off or unavailable.
"""

from app.ai.evidence import AiEvidenceBatchResult, AiEvidencePackage
from app.ai.package import PreparedAiImage
from app.ai.provider import (
    AiAssistRequest,
    AiAssistResponse,
    AiAvailability,
    AiProvider,
)


class NullAiProvider(AiProvider):
    """Always reports disabled/unavailable and never invents content."""

    def __init__(
        self,
        *,
        reason: str = "AI provider disabled or not configured",
        availability: AiAvailability = AiAvailability.DISABLED,
    ) -> None:
        self._reason = reason
        self._availability = availability

    @property
    def name(self) -> str:
        return "null"

    def availability(self) -> AiAvailability:
        return self._availability

    def assist(self, request: AiAssistRequest) -> AiAssistResponse:
        """Return an observable skip — does not call external services."""
        return AiAssistResponse(
            availability=self._availability,
            content=None,
            explanation=(
                f"AI assist skipped for task={request.task!r}. {self._reason}. "
                "Deterministic evidence and human review must be used instead."
            ),
            provider_name=self.name,
        )

    def recover_label_evidence(
        self,
        package: AiEvidencePackage,
        image: PreparedAiImage,
    ) -> AiEvidenceBatchResult:
        """Skip vision recovery observably."""
        _ = image
        return AiEvidenceBatchResult(
            availability=self._availability.value,
            provider_name=self.name,
            fields=[],
            explanation=(
                f"AI evidence recovery skipped ({len(package.fields)} field(s)). "
                f"{self._reason}"
            ),
            called=False,
        )
