"""
Deterministic overall-status aggregation and rule runner.

Architectural responsibility: run Phase 5 rules and aggregate PASS/REVIEW/FAIL.
"""

from __future__ import annotations

from app.models.verification import CheckStatus, FieldCheckResult, VerificationResult
from app.models.verification_mode import VerificationMode
from app.rules.alcohol_content import AlcoholContentRule
from app.rules.base import ComplianceRule, RuleContext
from app.rules.brand_name import BrandNameRule
from app.rules.class_type import ClassTypeRule
from app.rules.government_warning import GovernmentWarningRule
from app.rules.label_evidence import label_only_field_rules
from app.rules.net_contents import NetContentsRule


def default_rules() -> list[ComplianceRule]:
    """Ordered application-comparison rule set (Batch / future COLA)."""
    return [
        BrandNameRule(),
        ClassTypeRule(),
        AlcoholContentRule(),
        NetContentsRule(),
        GovernmentWarningRule(),
    ]


def rules_for_mode(mode: VerificationMode) -> list[ComplianceRule]:
    """
    Select rules for the verification context.

    LABEL_ONLY: field evidence + government warning (no application comparison).
    APPLICATION_COMPARISON: full compare rules + government warning.
    """
    if mode == VerificationMode.LABEL_ONLY:
        return [*label_only_field_rules(), GovernmentWarningRule()]
    return default_rules()


def aggregate_overall_status(checks: list[FieldCheckResult]) -> CheckStatus:
    """
    FAIL if any FAIL; else REVIEW if any REVIEW; else PASS.

    Prototype summary only — not a final regulatory determination.
    Counts only evaluated checks (omitted application-comparison rules are absent).
    """
    if any(c.status == CheckStatus.FAIL for c in checks):
        return CheckStatus.FAIL
    if any(c.status == CheckStatus.REVIEW for c in checks):
        return CheckStatus.REVIEW
    return CheckStatus.PASS


def run_rules(
    context: RuleContext,
    rules: list[ComplianceRule] | None = None,
) -> list[FieldCheckResult]:
    """Evaluate rules for the context mode (or an explicit rule list)."""
    selected = rules if rules is not None else rules_for_mode(context.mode)
    return [rule.evaluate(context) for rule in selected]


def build_verification_result(
    *,
    verification_id: str,
    checks: list[FieldCheckResult],
    processing_time_ms: float,
    stage_timings_ms: dict[str, float],
    degradation_notes: list[str] | None = None,
    verification_mode: str = "application_comparison",
) -> VerificationResult:
    """Assemble VerificationResult with counts and overall status."""
    overall = aggregate_overall_status(checks)
    return VerificationResult(
        verification_id=verification_id,
        product_class="distilled_spirits",
        verification_mode=verification_mode,
        overall_status=overall,
        checks=checks,
        pass_count=sum(1 for c in checks if c.status == CheckStatus.PASS),
        review_count=sum(1 for c in checks if c.status == CheckStatus.REVIEW),
        fail_count=sum(1 for c in checks if c.status == CheckStatus.FAIL),
        processing_time_ms=processing_time_ms,
        stage_timings_ms=stage_timings_ms,
        ai_used=False,
        ai_degraded=False,
        degradation_notes=degradation_notes
        or [
            "Deterministic verification summary only.",
        ],
    )
