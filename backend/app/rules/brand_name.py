"""
Brand name application-vs-label comparison rule.

Architectural responsibility: RULE-DS-BRAND-APP-COMPARE — consistency check only.
"""

from __future__ import annotations

from app.models.verification import CheckStatus, DecisionMethod, FieldCheckResult, ReviewReasonCode
from app.normalization.comparison import comparison_normalize, text_similarity
from app.rules.base import ComplianceRule, RuleContext
from app.rules.common import detection_from_field, extraction_gate
from app.rules.regulatory_sources import SOURCES


class BrandNameRule(ComplianceRule):
    """Compare application brand with extracted label brand."""

    @property
    def rule_id(self) -> str:
        return "RULE-DS-BRAND-APP-COMPARE"

    @property
    def check_name(self) -> str:
        return "Brand Name"

    def evaluate(self, context: RuleContext) -> FieldCheckResult:
        sources = [SOURCES["cfr_5_63"]["citation"], SOURCES["cfr_5_64"]["citation"]]
        if context.application is None:
            raise ValueError(
                "BrandNameRule requires application data (application-comparison mode)",
            )
        app_value = context.application.brand_name
        field = context.fields.get("brand_name")
        gated = extraction_gate(
            rule_id=self.rule_id,
            check_name=self.check_name,
            application_value=app_value,
            field=field,
            sources=sources,
            quality_status=context.quality_status,
        )
        if gated is not None:
            return gated

        assert field is not None  # for type checkers
        detected = field.raw_text or field.normalized_value
        sim = text_similarity(app_value, detected)
        details = {
            "similarity_ratio": sim.ratio,
            "pass_threshold": context.brand_pass_ratio,
            "review_threshold": context.brand_review_ratio,
            "normalized_application": sim.normalized_a,
            "normalized_detected": sim.normalized_b,
            "heuristic": "engineering fuzzy bands — not regulatory certainty",
        }

        if sim.exact_normalized or sim.ratio >= context.brand_pass_ratio:
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=app_value,
                expected_value=app_value,
                detected_label_value=detected,
                normalized_application_value=sim.normalized_a,
                normalized_detected_value=sim.normalized_b,
                status=CheckStatus.PASS,
                explanation=(
                    "Matches after case/whitespace normalization"
                    if sim.exact_normalized
                    else (
                        f"High-confidence near-match (similarity {sim.ratio:.1f}). "
                        "Engineering heuristic; not regulatory certainty."
                    )
                ),
                decision_method=(
                    DecisionMethod.NORMALIZED_COMPARISON
                    if sim.exact_normalized
                    else DecisionMethod.FUZZY_MATCH
                ),
                reason_code=ReviewReasonCode.BRAND_MATCH.value,
                ai_assist_eligible=False,
                detection_source=detection_from_field(field),
                authoritative_sources=sources,
                technical_details=details,
            )

        if sim.ratio >= context.brand_review_ratio:
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=app_value,
                expected_value=app_value,
                detected_label_value=detected,
                normalized_application_value=sim.normalized_a,
                normalized_detected_value=sim.normalized_b,
                status=CheckStatus.REVIEW,
                explanation=(
                    f"Ambiguous brand similarity ({sim.ratio:.1f}). "
                    "Human review required; not treated as automatic FAIL."
                ),
                decision_method=DecisionMethod.FUZZY_MATCH,
                reason_code=ReviewReasonCode.BRAND_AMBIGUOUS.value,
                ai_assist_eligible=True,
                detection_source=detection_from_field(field),
                authoritative_sources=sources,
                technical_details=details,
            )

        return FieldCheckResult(
            rule_id=self.rule_id,
            check_name=self.check_name,
            application_value=app_value,
            expected_value=app_value,
            detected_label_value=detected,
            normalized_application_value=comparison_normalize(app_value),
            normalized_detected_value=comparison_normalize(detected),
            status=CheckStatus.FAIL,
            explanation=(
                f"Detected brand differs from the application (similarity {sim.ratio:.1f}). "
                "Extraction was FOUND; treated as an objective mismatch for this prototype check."
            ),
            decision_method=DecisionMethod.FUZZY_MATCH,
            reason_code=ReviewReasonCode.BRAND_MISMATCH.value,
            ai_assist_eligible=False,
            detection_source=detection_from_field(field),
            authoritative_sources=sources,
            technical_details=details,
        )
