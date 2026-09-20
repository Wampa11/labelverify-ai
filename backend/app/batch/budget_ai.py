"""
Batch-scoped AI provider wrapper with call budget and concurrency limits.

Architectural responsibility: cost/capacity control for batch — does not change
eligibility rules; when budget is exhausted, availability becomes UNAVAILABLE so
VerificationService retains deterministic REVIEW.
"""

from __future__ import annotations

import threading

from app.ai.evidence import AiEvidenceBatchResult, AiEvidencePackage
from app.ai.package import PreparedAiImage
from app.ai.provider import (
    AiAssistRequest,
    AiAssistResponse,
    AiAvailability,
    AiProvider,
)


class BudgetAwareAiProvider(AiProvider):
    """Wraps an AiProvider; enforces max calls and optional AI concurrency semaphore."""

    def __init__(
        self,
        inner: AiProvider,
        *,
        max_calls: int,
        ai_concurrency: int = 1,
    ) -> None:
        self._inner = inner
        self._max_calls = max(0, max_calls)
        self._calls = 0
        self._lock = threading.Lock()
        self._sem = threading.Semaphore(max(1, ai_concurrency))
        self.budget_exhausted = False

    @property
    def name(self) -> str:
        return f"budget:{self._inner.name}"

    @property
    def calls_used(self) -> int:
        with self._lock:
            return self._calls

    def availability(self) -> AiAvailability:
        with self._lock:
            if self._max_calls <= 0 or self._calls >= self._max_calls:
                self.budget_exhausted = True
                return AiAvailability.UNAVAILABLE
        inner = self._inner.availability()
        if inner != AiAvailability.AVAILABLE:
            return inner
        return AiAvailability.AVAILABLE

    def assist(self, request: AiAssistRequest) -> AiAssistResponse:
        return AiAssistResponse(
            availability=self.availability(),
            content=None,
            explanation="Batch uses recover_label_evidence, not text assist.",
            provider_name=self.name,
        )

    def recover_label_evidence(
        self,
        package: AiEvidencePackage,
        image: PreparedAiImage,
    ) -> AiEvidenceBatchResult:
        with self._lock:
            if self._max_calls <= 0 or self._calls >= self._max_calls:
                self.budget_exhausted = True
                return AiEvidenceBatchResult(
                    availability=AiAvailability.UNAVAILABLE.value,
                    provider_name=self.name,
                    fields=[],
                    explanation=(
                        "AI_BUDGET_EXHAUSTED: batch AI call budget reached; "
                        "retaining deterministic REVIEW."
                    ),
                    called=False,
                    raw_error="AI_BUDGET_EXHAUSTED",
                )
            # Reserve a call slot before invoking inner.
            self._calls += 1
            remaining_ok = self._calls <= self._max_calls

        if not remaining_ok:
            self.budget_exhausted = True
            return AiEvidenceBatchResult(
                availability=AiAvailability.UNAVAILABLE.value,
                provider_name=self.name,
                fields=[],
                explanation=(
                    "AI_BUDGET_EXHAUSTED: batch AI call budget reached; "
                    "retaining deterministic REVIEW."
                ),
                called=False,
                raw_error="AI_BUDGET_EXHAUSTED",
            )

        with self._sem:
            if self._inner.availability() != AiAvailability.AVAILABLE:
                return AiEvidenceBatchResult(
                    availability=self._inner.availability().value,
                    provider_name=self.name,
                    fields=[],
                    explanation=(
                        "AI provider unavailable during batch; "
                        "retaining deterministic REVIEW."
                    ),
                    called=False,
                )
            return self._inner.recover_label_evidence(package, image)
