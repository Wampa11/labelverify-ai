"""
Scripted/mock AI provider for automated tests.

Architectural responsibility: deterministic fake vision evidence without network calls.
"""

from __future__ import annotations

from app.ai.evidence import (
    AiEvidenceBatchResult,
    AiEvidencePackage,
    AiFieldEvidence,
)
from app.ai.package import PreparedAiImage
from app.ai.provider import (
    AiAssistRequest,
    AiAssistResponse,
    AiAvailability,
    AiProvider,
)


class ScriptedAiProvider(AiProvider):
    """Returns preconfigured field evidence; counts calls for budget tests."""

    def __init__(
        self,
        *,
        results: list[AiFieldEvidence] | None = None,
        availability: AiAvailability = AiAvailability.AVAILABLE,
        error: str | None = None,
        latency_ms: float = 12.0,
        raise_on_call: Exception | None = None,
    ) -> None:
        self._results = list(results or [])
        self._availability = availability
        self._error = error
        self._latency_ms = latency_ms
        self._raise_on_call = raise_on_call
        self.calls = 0
        self.last_package: AiEvidencePackage | None = None
        self.last_image: PreparedAiImage | None = None

    @property
    def name(self) -> str:
        return "scripted"

    def availability(self) -> AiAvailability:
        return self._availability

    def assist(self, request: AiAssistRequest) -> AiAssistResponse:
        self.calls += 1
        return AiAssistResponse(
            availability=self._availability,
            content=None,
            explanation=f"scripted assist for {request.task}",
            provider_name=self.name,
        )

    def recover_label_evidence(
        self,
        package: AiEvidencePackage,
        image: PreparedAiImage,
    ) -> AiEvidenceBatchResult:
        self.calls += 1
        self.last_package = package
        self.last_image = image
        if self._raise_on_call is not None:
            raise self._raise_on_call
        if self._availability != AiAvailability.AVAILABLE:
            return AiEvidenceBatchResult(
                availability=self._availability.value,
                provider_name=self.name,
                fields=[],
                explanation=self._error or "scripted provider not available",
                called=False,
            )
        if self._error:
            return AiEvidenceBatchResult(
                availability=AiAvailability.UNAVAILABLE.value,
                provider_name=self.name,
                fields=[],
                explanation=self._error,
                latency_ms=self._latency_ms,
                raw_error=self._error,
                called=True,
            )
        # Filter results to requested fields when provided.
        requested = {item.field for item in package.fields}
        fields = [f for f in self._results if f.field in requested] or list(self._results)
        return AiEvidenceBatchResult(
            availability=AiAvailability.AVAILABLE.value,
            provider_name=self.name,
            model="scripted-model",
            fields=fields,
            explanation="scripted evidence recovery",
            latency_ms=self._latency_ms,
            called=True,
        )
