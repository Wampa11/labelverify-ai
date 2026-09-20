"""
Alcohol content application comparison and mandatory % ABV format gate.

Architectural responsibility: RULE-DS-ABV-APP-COMPARE-AND-FORMAT per 27 CFR § 5.65.
"""

from __future__ import annotations

from app.models.verification import CheckStatus, DecisionMethod, FieldCheckResult, ReviewReasonCode
from app.normalization.comparison import (
    has_authorized_percent_abv_statement,
    parse_application_abv,
)
from app.rules.base import ComplianceRule, RuleContext
from app.rules.common import detection_from_field, extraction_gate
from app.rules.regulatory_sources import SOURCES


class AlcoholContentRule(ComplianceRule):
    """Compare application ABV with extracted label ABV; require % ABV statement form."""

    @property
    def rule_id(self) -> str:
        return "RULE-DS-ABV-APP-COMPARE-AND-FORMAT"

    @property
    def check_name(self) -> str:
        return "Alcohol Content / ABV"

    def evaluate(self, context: RuleContext) -> FieldCheckResult:
        sources = [SOURCES["cfr_5_65"]["citation"], SOURCES["cfr_5_63"]["citation"]]
        if context.application is None:
            raise ValueError(
                "AlcoholContentRule requires application data (application-comparison mode)",
            )
        app_value = context.application.alcohol_content_abv
        field = context.fields.get("alcohol_content")
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
        app_abv = parse_application_abv(app_value)
        if app_abv is None:
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=app_value,
                expected_value=app_value,
                detected_label_value=detected,
                status=CheckStatus.REVIEW,
                explanation="Application alcohol content could not be parsed as a percentage ABV.",
                decision_method=DecisionMethod.HUMAN_REVIEW_REQUIRED,
                reason_code=ReviewReasonCode.APPLICATION_VALUE_INVALID.value,
                ai_assist_eligible=False,
                detection_source=detection_from_field(field),
                authoritative_sources=sources,
            )

        label_abv = field.normalized_numeric
        if label_abv is None:
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=app_value,
                expected_value=f"{app_abv:g}%",
                detected_label_value=detected,
                status=CheckStatus.REVIEW,
                explanation="Label alcohol content lacked a usable numeric ABV.",
                decision_method=DecisionMethod.HUMAN_REVIEW_REQUIRED,
                reason_code=ReviewReasonCode.EXTRACTION_UNCERTAIN.value,
                ai_assist_eligible=True,
                detection_source=detection_from_field(field),
                authoritative_sources=sources,
            )

        if not has_authorized_percent_abv_statement(field.raw_text):
            explanation_l = (field.explanation or "").lower()
            raw_l = (field.raw_text or "").lower()
            if "proof" in explanation_l and "alc" not in raw_l and "%" not in raw_l:
                return FieldCheckResult(
                    rule_id=self.rule_id,
                    check_name=self.check_name,
                    application_value=app_value,
                    expected_value=f"{app_abv:g}% alcohol by volume",
                    detected_label_value=detected,
                    status=CheckStatus.REVIEW,
                    explanation=(
                        "Label evidence shows proof (or proof-derived strength) without a clear "
                        "mandatory percentage alcohol-by-volume statement (27 CFR § 5.65). "
                        "Proof alone does not satisfy the mandatory % ABV statement "
                        "in this prototype."
                    ),
                    decision_method=DecisionMethod.DETERMINISTIC_RULE,
                    reason_code=ReviewReasonCode.PROOF_ONLY_NO_PERCENT_STATEMENT.value,
                    ai_assist_eligible=True,
                    detection_source=detection_from_field(field),
                    authoritative_sources=sources,
                    limitations=[
                        "Does not geometrically verify same-field-of-vision placement of proof.",
                    ],
                )
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=app_value,
                expected_value=f"{app_abv:g}% alcohol by volume",
                detected_label_value=detected,
                status=CheckStatus.REVIEW,
                explanation=(
                    "Recovered alcohol strength, but OCR evidence does not clearly show an "
                    "authorized percentage alcohol-by-volume statement format under 27 CFR § 5.65."
                ),
                decision_method=DecisionMethod.DETERMINISTIC_RULE,
                reason_code=ReviewReasonCode.ABV_FORMAT_REVIEW.value,
                ai_assist_eligible=True,
                detection_source=detection_from_field(field),
                authoritative_sources=sources,
            )

        delta = abs(app_abv - label_abv)
        details = {
            "application_abv": app_abv,
            "label_abv": label_abv,
            "delta_pp": delta,
            "epsilon_pp": context.abv_epsilon,
        }
        if delta <= context.abv_epsilon:
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=app_value,
                expected_value=f"{app_abv:g}%",
                detected_label_value=detected,
                normalized_application_value=f"{app_abv:g}",
                normalized_detected_value=f"{label_abv:g}",
                status=CheckStatus.PASS,
                explanation=(
                    f"Application ABV {app_abv:g}% matches label ABV {label_abv:g}% "
                    f"(difference {delta:.3f} pp within epsilon {context.abv_epsilon})."
                ),
                decision_method=DecisionMethod.NORMALIZED_COMPARISON,
                reason_code=ReviewReasonCode.ABV_MATCH.value,
                ai_assist_eligible=False,
                detection_source=detection_from_field(field),
                authoritative_sources=sources,
                technical_details=details,
            )

        return FieldCheckResult(
            rule_id=self.rule_id,
            check_name=self.check_name,
            application_value=app_value,
            expected_value=f"{app_abv:g}%",
            detected_label_value=detected,
            normalized_application_value=f"{app_abv:g}",
            normalized_detected_value=f"{label_abv:g}",
            status=CheckStatus.FAIL,
            explanation=(
                f"Detected alcohol content ({label_abv:g}%) differs from the application "
                f"({app_abv:g}%) by {delta:.3f} percentage points."
            ),
            decision_method=DecisionMethod.NORMALIZED_COMPARISON,
            reason_code=ReviewReasonCode.ABV_MISMATCH.value,
            ai_assist_eligible=False,
            detection_source=detection_from_field(field),
            authoritative_sources=sources,
            technical_details=details,
        )
