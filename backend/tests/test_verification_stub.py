"""
Verification model and stub service tests.

Architectural responsibility: ensure result contracts and stub orchestration stay reviewable.
"""

from app.models.verification import ApplicationData, CheckStatus, DecisionMethod
from app.services.verification_service import INITIAL_CHECK_NAMES, VerificationService


def test_stub_verification_returns_review_for_all_initial_checks() -> None:
    """Stub without image should mark every initial check as REVIEW with explanations."""
    service = VerificationService()
    result = service.verify_stub(
        ApplicationData(
            brand_name="Example Spirits",
            class_type="Vodka",
            alcohol_content_abv="40%",
            net_contents="750 mL",
        ),
    )
    assert result.overall_status == CheckStatus.REVIEW
    assert result.processing_time_ms >= 0
    assert len(result.checks) == len(INITIAL_CHECK_NAMES)
    assert all(check.status == CheckStatus.REVIEW for check in result.checks)
    assert all(check.explanation for check in result.checks)
    assert all(check.decision_method == DecisionMethod.PIPELINE_STUB for check in result.checks)
    assert all(check.confidence is None for check in result.checks)
    assert result.disclaimer
