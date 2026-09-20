"""
Net contents application-vs-label comparison rule.

Architectural responsibility: RULE-DS-NET-CONTENTS-APP-COMPARE per 27 CFR § 5.70.
"""

from __future__ import annotations

from app.models.verification import CheckStatus, DecisionMethod, FieldCheckResult, ReviewReasonCode
from app.normalization.comparison import (
    parse_application_net_ml,
    to_milliliters,
    volumes_equal_ml,
)
from app.normalization.field_parsers import parse_net_contents
from app.rules.base import ComplianceRule, RuleContext
from app.rules.common import detection_from_field, extraction_gate
from app.rules.regulatory_sources import SOURCES


class NetContentsRule(ComplianceRule):
    """Compare application net contents with extracted label volume."""

    @property
    def rule_id(self) -> str:
        return "RULE-DS-NET-CONTENTS-APP-COMPARE"

    @property
    def check_name(self) -> str:
        return "Net Contents"

    def evaluate(self, context: RuleContext) -> FieldCheckResult:
        sources = [SOURCES["cfr_5_70"]["citation"], SOURCES["cfr_5_63"]["citation"]]
        if context.application is None:
            raise ValueError(
                "NetContentsRule requires application data (application-comparison mode)",
            )
        app_value = context.application.net_contents
        field = context.fields.get("net_contents")
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
        app_ml = parse_application_net_ml(app_value)
        if app_ml is None:
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=app_value,
                expected_value=app_value,
                detected_label_value=detected,
                status=CheckStatus.REVIEW,
                explanation="Application net contents could not be parsed as a volume.",
                decision_method=DecisionMethod.HUMAN_REVIEW_REQUIRED,
                reason_code=ReviewReasonCode.APPLICATION_VALUE_INVALID.value,
                ai_assist_eligible=False,
                detection_source=detection_from_field(field),
                authoritative_sources=sources,
            )

        if field.normalized_numeric is not None and field.normalized_unit:
            label_ml = to_milliliters(field.normalized_numeric, field.normalized_unit)
        else:
            parsed = parse_net_contents(detected or "")
            if parsed is None:
                return FieldCheckResult(
                    rule_id=self.rule_id,
                    check_name=self.check_name,
                    application_value=app_value,
                    expected_value=app_value,
                    detected_label_value=detected,
                    status=CheckStatus.REVIEW,
                    explanation="Label net contents lacked a usable quantity/unit.",
                    decision_method=DecisionMethod.HUMAN_REVIEW_REQUIRED,
                    reason_code=ReviewReasonCode.EXTRACTION_UNCERTAIN.value,
                    ai_assist_eligible=True,
                    detection_source=detection_from_field(field),
                    authoritative_sources=sources,
                )
            label_ml = to_milliliters(parsed.value, parsed.unit)

        details = {
            "application_ml": app_ml,
            "label_ml": label_ml,
            "epsilon_ml": context.net_ml_epsilon,
        }
        if volumes_equal_ml(app_ml, label_ml, epsilon_ml=context.net_ml_epsilon):
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=app_value,
                expected_value=app_value,
                detected_label_value=detected,
                normalized_application_value=f"{app_ml:g} mL",
                normalized_detected_value=f"{label_ml:g} mL",
                status=CheckStatus.PASS,
                explanation=(
                    f"Net contents match after unit normalization "
                    f"({app_ml:g} mL ≈ {label_ml:g} mL)."
                ),
                decision_method=DecisionMethod.NORMALIZED_COMPARISON,
                reason_code=ReviewReasonCode.NET_CONTENTS_MATCH.value,
                ai_assist_eligible=False,
                detection_source=detection_from_field(field),
                authoritative_sources=sources,
                technical_details=details,
                limitations=["Does not verify type size from image pixels."],
            )

        return FieldCheckResult(
            rule_id=self.rule_id,
            check_name=self.check_name,
            application_value=app_value,
            expected_value=app_value,
            detected_label_value=detected,
            normalized_application_value=f"{app_ml:g} mL",
            normalized_detected_value=f"{label_ml:g} mL",
            status=CheckStatus.FAIL,
            explanation=(
                f"Detected net contents ({label_ml:g} mL) differ from the application "
                f"({app_ml:g} mL)."
            ),
            decision_method=DecisionMethod.NORMALIZED_COMPARISON,
            reason_code=ReviewReasonCode.NET_CONTENTS_MISMATCH.value,
            ai_assist_eligible=False,
            detection_source=detection_from_field(field),
            authoritative_sources=sources,
            technical_details=details,
        )
