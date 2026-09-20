"""
Label-only field evidence checks (no application comparison).

Architectural responsibility: assess whether mandatory label information appears recoverable
from the image for LABEL_ONLY Single Review — never invent application mismatches.
"""

from __future__ import annotations

from app.models.verification import CheckStatus, DecisionMethod, FieldCheckResult, ReviewReasonCode
from app.normalization.comparison import has_authorized_percent_abv_statement
from app.rules.base import ComplianceRule, RuleContext
from app.rules.common import detection_from_field, display_detected_value, extraction_gate
from app.rules.regulatory_sources import SOURCES


class LabelFieldEvidenceRule(ComplianceRule):
    """
    Presence/readability of one extracted field on the label.

    PASS when FOUND (and ABV format OK when applicable). REVIEW when uncertain/missing.
    Never FAIL solely because application data was not supplied.
    """

    def __init__(
        self,
        *,
        rule_id: str,
        check_name: str,
        field_key: str,
        source_keys: tuple[str, ...],
    ) -> None:
        self._rule_id = rule_id
        self._check_name = check_name
        self._field_key = field_key
        self._source_keys = source_keys

    @property
    def rule_id(self) -> str:
        return self._rule_id

    @property
    def check_name(self) -> str:
        return self._check_name

    def evaluate(self, context: RuleContext) -> FieldCheckResult:
        sources = [SOURCES[k]["citation"] for k in self._source_keys if k in SOURCES]
        field = context.fields.get(self._field_key)
        gated = extraction_gate(
            rule_id=self.rule_id,
            check_name=self.check_name,
            application_value=None,
            field=field,
            sources=sources,
            quality_status=context.quality_status,
        )
        if gated is not None:
            return gated.model_copy(
                update={
                    "technical_details": {
                        **(gated.technical_details or {}),
                        "verification_mode": "label_only",
                        "field_key": self._field_key,
                    },
                },
            )

        assert field is not None
        detected = display_detected_value(field)

        if self._field_key == "alcohol_content":
            evidence_text = " ".join(
                part for part in (field.raw_text, field.normalized_value) if part
            )
            if not has_authorized_percent_abv_statement(evidence_text):
                explanation_l = (field.explanation or "").lower()
                raw_l = evidence_text.lower()
                if "proof" in explanation_l or (
                    "proof" in raw_l and "alc" not in raw_l and "%" not in (field.raw_text or "")
                ):
                    return FieldCheckResult(
                        rule_id=self.rule_id,
                        check_name=self.check_name,
                        application_value=None,
                        expected_value="Percentage alcohol-by-volume statement",
                        detected_label_value=detected,
                        status=CheckStatus.REVIEW,
                        explanation=(
                            "Proof was recovered without a clear percentage "
                            "alcohol-by-volume statement."
                        ),
                        decision_method=DecisionMethod.DETERMINISTIC_RULE,
                        reason_code=ReviewReasonCode.PROOF_ONLY_NO_PERCENT_STATEMENT.value,
                        ai_assist_eligible=True,
                        detection_source=detection_from_field(field),
                        authoritative_sources=sources,
                        technical_details={
                            "verification_mode": "label_only",
                            "raw_ocr": field.raw_text,
                            "normalized_value": field.normalized_value,
                            "extractor_explanation": field.explanation,
                        },
                    )
                return FieldCheckResult(
                    rule_id=self.rule_id,
                    check_name=self.check_name,
                    application_value=None,
                    expected_value="Percentage alcohol-by-volume statement",
                    detected_label_value=detected,
                    status=CheckStatus.REVIEW,
                    explanation="Alcohol content could not be reliably extracted.",
                    decision_method=DecisionMethod.DETERMINISTIC_RULE,
                    reason_code=ReviewReasonCode.ABV_FORMAT_REVIEW.value,
                    ai_assist_eligible=True,
                    detection_source=detection_from_field(field),
                    authoritative_sources=sources,
                    technical_details={
                        "verification_mode": "label_only",
                        "raw_ocr": field.raw_text,
                        "normalized_value": field.normalized_value,
                    },
                )

        return FieldCheckResult(
            rule_id=self.rule_id,
            check_name=self.check_name,
            application_value=None,
            expected_value=None,
            detected_label_value=detected,
            normalized_detected_value=comparison_normalize_safe(detected),
            status=CheckStatus.PASS,
            explanation=_pass_explanation(self._field_key, detected),
            decision_method=DecisionMethod.DETERMINISTIC_RULE,
            reason_code=_pass_reason(self._field_key),
            ai_assist_eligible=False,
            detection_source=detection_from_field(field),
            authoritative_sources=sources,
            technical_details={
                "verification_mode": "label_only",
                "field_key": self._field_key,
                "raw_ocr": field.raw_text,
                "normalized_value": field.normalized_value,
                "extraction_method": field.extraction_method.value,
                "extractor_explanation": field.explanation,
                "candidates": list(field.candidates or []),
                "ai_fallback_hints": field.ai_fallback_hints,
            },
        )


def comparison_normalize_safe(text: str | None) -> str | None:
    if not text:
        return None
    from app.normalization.comparison import comparison_normalize

    return comparison_normalize(text)


def _pass_reason(field_key: str) -> str:
    return {
        "brand_name": ReviewReasonCode.BRAND_MATCH.value,
        "class_type": ReviewReasonCode.CLASS_TYPE_MATCH.value,
        "alcohol_content": ReviewReasonCode.ABV_MATCH.value,
        "net_contents": ReviewReasonCode.NET_CONTENTS_MATCH.value,
    }.get(field_key, ReviewReasonCode.BRAND_MATCH.value)


def _pass_explanation(field_key: str, detected: str | None) -> str:
    if field_key == "net_contents" and detected:
        return f"Net contents were recovered as {detected}."
    if field_key == "brand_name" and detected:
        return f"Brand name was recovered as {detected}."
    if field_key == "class_type" and detected:
        return f"Class/type was recovered as {detected}."
    if field_key == "alcohol_content" and detected:
        return f"Alcohol content was recovered as {detected}."
    return "Recovered from the label image."


def label_only_field_rules() -> list[ComplianceRule]:
    """Mandatory label information evidence checks for LABEL_ONLY mode."""
    return [
        LabelFieldEvidenceRule(
            rule_id="RULE-DS-BRAND-LABEL-EVIDENCE",
            check_name="Brand Name",
            field_key="brand_name",
            source_keys=("cfr_5_63", "cfr_5_64"),
        ),
        LabelFieldEvidenceRule(
            rule_id="RULE-DS-CLASS-TYPE-LABEL-EVIDENCE",
            check_name="Class / Type",
            field_key="class_type",
            source_keys=("cfr_5_63",),
        ),
        LabelFieldEvidenceRule(
            rule_id="RULE-DS-ABV-LABEL-EVIDENCE",
            check_name="Alcohol Content / ABV",
            field_key="alcohol_content",
            source_keys=("cfr_5_65", "cfr_5_63"),
        ),
        LabelFieldEvidenceRule(
            rule_id="RULE-DS-NET-CONTENTS-LABEL-EVIDENCE",
            check_name="Net Contents",
            field_key="net_contents",
            source_keys=("cfr_5_70", "cfr_5_63"),
        ),
    ]
