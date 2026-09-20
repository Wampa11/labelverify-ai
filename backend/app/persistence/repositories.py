"""
Repository interfaces for verification and batch records.

Architectural responsibility: persistence API used by services — no HTTP or OCR concerns.
"""

from app.core.exceptions import NotImplementedStageError
from app.models.verification import VerificationResult


class VerificationRepository:
    """Stores and loads verification results. Phase 1: seam only."""

    def save(self, result: VerificationResult) -> str:
        """Persist a verification result and return its id. Not implemented yet."""
        raise NotImplementedStageError(
            "VerificationRepository.save is not implemented in Phase 1",
            details=f"overall_status={result.overall_status}",
        )

    def get(self, verification_id: str) -> VerificationResult:
        """Load a verification result by id. Not implemented yet."""
        raise NotImplementedStageError(
            "VerificationRepository.get is not implemented in Phase 1",
            details=f"verification_id={verification_id!r}",
        )
