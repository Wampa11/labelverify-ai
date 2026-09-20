"""
Class/type application-vs-label comparison rule (conservative).

Architectural responsibility: RULE-DS-CLASS-TYPE-APP-COMPARE —
does not implement full standards of identity.
"""

from __future__ import annotations

from app.models.verification import CheckStatus, DecisionMethod, FieldCheckResult, ReviewReasonCode
from app.normalization.comparison import comparison_normalize, text_similarity
from app.rules.base import ComplianceRule, RuleContext
from app.rules.common import detection_from_field, extraction_gate
from app.rules.regulatory_sources import SOURCES

# Clear category contradictions used only when both sides are FOUND and dissimilar.
_CATEGORY_TOKENS = (
    "bourbon",
    "whiskey",
    "whisky",
    "vodka",
    "gin",
    "rum",
    "tequila",
    "mezcal",
    "brandy",
    "cognac",
    "liqueur",
)


class ClassTypeRule(ComplianceRule):
    """Compare application class/type with extracted label class/type."""

    @property
    def rule_id(self) -> str:
        return "RULE-DS-CLASS-TYPE-APP-COMPARE"

    @property
    def check_name(self) -> str:
        return "Class / Type"

    def evaluate(self, context: RuleContext) -> FieldCheckResult:
        sources = [
            SOURCES["cfr_5_63"]["citation"],
            SOURCES["cfr_5_subpart_i"]["citation"],
        ]
        if context.application is None:
            raise ValueError(
                "ClassTypeRule requires application data (application-comparison mode)",
            )
        app_value = context.application.class_type
        field = context.fields.get("class_type")
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

        assert field is not None
        detected = field.raw_text or field.normalized_value
        sim = text_similarity(app_value, detected)
        details = {
            "similarity_ratio": sim.ratio,
            "pass_threshold": context.class_pass_ratio,
            "normalized_application": sim.normalized_a,
            "normalized_detected": sim.normalized_b,
            "heuristic": "conservative class/type bands — not full Subpart I classification",
        }

        if sim.exact_normalized:
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=app_value,
                expected_value=app_value,
                detected_label_value=detected,
                normalized_application_value=sim.normalized_a,
                normalized_detected_value=sim.normalized_b,
                status=CheckStatus.PASS,
                explanation="Class/type matches after case/whitespace normalization.",
                decision_method=DecisionMethod.NORMALIZED_COMPARISON,
                reason_code=ReviewReasonCode.CLASS_TYPE_MATCH.value,
                ai_assist_eligible=False,
                detection_source=detection_from_field(field),
                authoritative_sources=sources,
                technical_details=details,
            )

        if sim.ratio >= context.class_pass_ratio:
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
                    f"Near-exact class/type match after OCR-tolerant comparison "
                    f"(similarity {sim.ratio:.1f}). Engineering heuristic only."
                ),
                decision_method=DecisionMethod.FUZZY_MATCH,
                reason_code=ReviewReasonCode.CLASS_TYPE_MATCH.value,
                ai_assist_eligible=False,
                detection_source=detection_from_field(field),
                authoritative_sources=sources,
                technical_details=details,
            )

        if _clear_category_conflict(sim.normalized_a, sim.normalized_b) and sim.ratio < 70:
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=app_value,
                expected_value=app_value,
                detected_label_value=detected,
                normalized_application_value=sim.normalized_a,
                normalized_detected_value=sim.normalized_b,
                status=CheckStatus.FAIL,
                explanation=(
                    "Detected class/type appears to be a different spirit category than "
                    f"the application (similarity {sim.ratio:.1f})."
                ),
                decision_method=DecisionMethod.NORMALIZED_COMPARISON,
                reason_code=ReviewReasonCode.CLASS_TYPE_MISMATCH.value,
                ai_assist_eligible=False,
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
            status=CheckStatus.REVIEW,
            explanation=(
                "Class/type text does not confidently match the full application designation. "
                "Partial OCR recovery or legally meaningful wording differences require "
                f"human review (similarity {sim.ratio:.1f})."
            ),
            decision_method=DecisionMethod.HUMAN_REVIEW_REQUIRED,
            reason_code=ReviewReasonCode.CLASS_TYPE_AMBIGUOUS.value,
            ai_assist_eligible=True,
            detection_source=detection_from_field(field),
            authoritative_sources=sources,
            technical_details=details,
            limitations=[
                "Does not implement full 27 CFR Part 5 Subpart I standards of identity.",
            ],
        )


def _clear_category_conflict(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    cats_a = {t for t in _CATEGORY_TOKENS if t in a}
    cats_b = {t for t in _CATEGORY_TOKENS if t in b}
    family = {"whiskey", "whisky", "bourbon"}
    cats_a = {("whiskey_family" if c in family else c) for c in cats_a}
    cats_b = {("whiskey_family" if c in family else c) for c in cats_b}
    if not cats_a or not cats_b:
        return False
    return cats_a.isdisjoint(cats_b)
