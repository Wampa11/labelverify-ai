"""
Confidence policy skeleton.

Architectural responsibility: prefer REVIEW under ambiguity; never fabricate confidence numbers.
"""

from app.core.exceptions import NotImplementedStageError
from app.models.verification import CheckStatus, FieldCheckResult


class ConfidenceEvaluator:
    """Applies confidence / ambiguity policy to check results. Phase 1: seam only."""

    def apply(self, check: FieldCheckResult) -> FieldCheckResult:
        """
        Adjust status when confidence/ambiguity requires REVIEW.

        Not implemented in Phase 1.
        """
        raise NotImplementedStageError(
            "Confidence evaluation is not implemented in Phase 1",
            details=f"check_name={check.check_name!r} status={check.status}",
        )

    def prefer_review_when_uncertain(
        self,
        status: CheckStatus,
        *,
        confidence: float | None,
        uncertain: bool,
    ) -> CheckStatus:
        """
        Illustrative policy helper documenting the REVIEW bias.

        Does not invent confidence; only reacts to provided signals.
        """
        if uncertain:
            return CheckStatus.REVIEW
        if confidence is not None and status == CheckStatus.FAIL:
            # Thresholds will be chosen and documented later — not treated as truth here.
            return status
        return status
