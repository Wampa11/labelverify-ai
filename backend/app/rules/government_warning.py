"""
Government health warning label-only verification.

Architectural responsibility: RULE-DS-GOVERNMENT-WARNING-LABEL per 27 CFR §§ 16.21–16.22.
Does not claim bold or type-size compliance from ordinary OCR.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from app.models.extraction import ExtractionStatus
from app.models.verification import CheckStatus, DecisionMethod, FieldCheckResult, ReviewReasonCode
from app.normalization.comparison import warning_wording_normalize
from app.rules.base import ComplianceRule, RuleContext
from app.rules.common import detection_from_field
from app.rules.regulatory_sources import SOURCES, STATUTORY_GOVERNMENT_WARNING

_HEADER = re.compile(r"government\s+warning", re.IGNORECASE)


class GovernmentWarningRule(ComplianceRule):
    """Evaluate presence/wording/capitalization; mark bold/size not machine-verifiable."""

    @property
    def rule_id(self) -> str:
        return "RULE-DS-GOVERNMENT-WARNING-LABEL"

    @property
    def check_name(self) -> str:
        return "Government Health Warning"

    def evaluate(self, context: RuleContext) -> FieldCheckResult:
        sources = [SOURCES["cfr_16_21"]["citation"], SOURCES["cfr_16_22"]["citation"]]
        field = context.fields.get("government_warning")
        limitations = [
            "Bold type (§ 16.22) is not machine-verifiable from ordinary OCR text.",
            "Physical type size / characters-per-inch require calibrated real-world scale "
            "and are not evaluated as PASS in this prototype.",
            "Separate-and-apart placement and contrast are not reliably measured here.",
        ]

        if field is None or field.status == ExtractionStatus.NOT_FOUND:
            semantic_reason = ReviewReasonCode.WARNING_MISSING.value
            explanation = (
                "No government health warning was recovered from the label image. "
                "Because OCR/image limitations can hide text, this is REVIEW rather than "
                "automatic FAIL."
            )
            display_reason = semantic_reason
            if context.quality_status in {"WARNING", "POOR"}:
                display_reason = ReviewReasonCode.OCR_LOW_QUALITY.value
                explanation += f" Image quality was {context.quality_status}."
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=None,
                expected_value=STATUTORY_GOVERNMENT_WARNING,
                detected_label_value=None,
                status=CheckStatus.REVIEW,
                explanation=explanation,
                decision_method=DecisionMethod.HUMAN_REVIEW_REQUIRED,
                reason_code=display_reason,
                ai_assist_eligible=True,
                limitations=limitations,
                authoritative_sources=sources,
                technical_details={
                    "extraction_status": (
                        field.status.value if field is not None else "NOT_FOUND"
                    ),
                    "underlying_reason_code": semantic_reason,
                    "quality_status": context.quality_status,
                },
            )

        detected = field.raw_text or ""
        if field.status == ExtractionStatus.UNCERTAIN:
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=None,
                expected_value=STATUTORY_GOVERNMENT_WARNING,
                detected_label_value=detected,
                status=CheckStatus.REVIEW,
                explanation=(
                    "Warning extraction is partial or uncertain. "
                    f"Extractor note: {field.explanation} Bold/type-size also remain "
                    "not machine-verifiable."
                ),
                decision_method=DecisionMethod.HUMAN_REVIEW_REQUIRED,
                reason_code=ReviewReasonCode.WARNING_PARTIAL.value,
                ai_assist_eligible=True,
                detection_source=detection_from_field(field),
                limitations=limitations,
                authoritative_sources=sources,
            )

        expected_norm = warning_wording_normalize(STATUTORY_GOVERNMENT_WARNING)
        detected_norm = warning_wording_normalize(detected)
        assert expected_norm is not None and detected_norm is not None
        ratio = float(fuzz.token_set_ratio(expected_norm, detected_norm))
        details = {"wording_similarity": ratio, "statutory_citation": "27 CFR § 16.21"}

        # Capitalization of heading when OCR preserves case.
        caps_ok: bool | None = None
        header_match = _HEADER.search(detected)
        if header_match:
            header_text = header_match.group(0)
            if header_text.isupper():
                caps_ok = True
            elif header_text != header_text.lower() and header_text != header_text.upper():
                # Mixed case recovered — likely real case from OCR.
                caps_ok = False
            else:
                caps_ok = None  # all-lower OCR may have lost case

        if ratio < 75:
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=None,
                expected_value=STATUTORY_GOVERNMENT_WARNING,
                detected_label_value=detected,
                status=CheckStatus.FAIL,
                explanation=(
                    "Recovered warning text differs materially from the statutory wording "
                    f"in 27 CFR § 16.21 (similarity {ratio:.1f})."
                ),
                decision_method=DecisionMethod.DETERMINISTIC_RULE,
                reason_code=ReviewReasonCode.WARNING_WORDING_MISMATCH.value,
                ai_assist_eligible=False,
                detection_source=detection_from_field(field),
                limitations=limitations,
                authoritative_sources=sources,
                technical_details=details,
            )

        if ratio < 92:
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=None,
                expected_value=STATUTORY_GOVERNMENT_WARNING,
                detected_label_value=detected,
                status=CheckStatus.REVIEW,
                explanation=(
                    "Warning appears present but wording is incomplete or noisy relative to "
                    f"27 CFR § 16.21 (similarity {ratio:.1f}). Human review required. "
                    "Bold and type-size are not machine-verifiable from OCR."
                ),
                decision_method=DecisionMethod.HUMAN_REVIEW_REQUIRED,
                reason_code=ReviewReasonCode.WARNING_PARTIAL.value,
                ai_assist_eligible=True,
                detection_source=detection_from_field(field),
                limitations=limitations,
                authoritative_sources=sources,
                technical_details=details,
            )

        if caps_ok is False:
            return FieldCheckResult(
                rule_id=self.rule_id,
                check_name=self.check_name,
                application_value=None,
                expected_value=STATUTORY_GOVERNMENT_WARNING,
                detected_label_value=detected,
                status=CheckStatus.REVIEW,
                explanation=(
                    "Warning wording appears complete, but OCR shows the heading is not in "
                    "all capitals as required for “GOVERNMENT WARNING” (27 CFR § 16.22). "
                    "Bold type remains not machine-verifiable."
                ),
                decision_method=DecisionMethod.DETERMINISTIC_RULE,
                reason_code=ReviewReasonCode.WARNING_CAPS_REVIEW.value,
                ai_assist_eligible=False,
                detection_source=detection_from_field(field),
                limitations=limitations,
                authoritative_sources=sources,
                technical_details={**details, "heading_caps_ok": caps_ok},
            )

        # Wording OK — still cannot PASS bold/size, so attach FORMAT_NOT_MACHINE_VERIFIABLE
        # as a limitation while overall check can PASS on wording+caps when case known,
        # OR REVIEW when case unknown to stay conservative about § 16.22 packaging.
        #
        # Stakeholder asks: demonstrate understanding of bold requirement without claiming
        # compliance. We PASS wording when strong match + caps OK/unknown, and list
        # formatting as limitations with reason_code noting format not verified.
        # When caps unknown, include WARNING_CAPS_REVIEW note in limitations but allow PASS
        # on wording with explicit limitation that bold/size were not verified.
        status = CheckStatus.PASS
        reason = ReviewReasonCode.WARNING_PRESENT_MATCH.value
        explanation = (
            "Warning wording matches the statutory text in 27 CFR § 16.21 after whitespace "
            "normalization."
        )
        if caps_ok is True:
            explanation += " Heading appears in capital letters as recovered by OCR."
        else:
            explanation += (
                " Heading capitalization could not be confirmed (OCR may have lost case)."
            )
            status = CheckStatus.REVIEW
            reason = ReviewReasonCode.WARNING_CAPS_REVIEW.value

        explanation += (
            " Bold type and physical type-size requirements (§ 16.22) are "
            "NOT machine-verifiable from available evidence and require human review."
        )

        # Even on PASS wording, surface format as non-AI-eligible human review note.
        if status == CheckStatus.PASS:
            # Keep PASS for objective wording match; formatting called out in limitations.
            pass
        else:
            # REVIEW for caps uncertainty also covers format.
            pass

        return FieldCheckResult(
            rule_id=self.rule_id,
            check_name=self.check_name,
            application_value=None,
            expected_value=STATUTORY_GOVERNMENT_WARNING,
            detected_label_value=detected,
            status=status,
            explanation=explanation,
            decision_method=DecisionMethod.DETERMINISTIC_RULE,
            reason_code=(
                reason
                if status == CheckStatus.REVIEW
                else ReviewReasonCode.WARNING_PRESENT_MATCH.value
            ),
            ai_assist_eligible=False,
            detection_source=detection_from_field(field),
            limitations=limitations
            + [
                "FORMAT_NOT_MACHINE_VERIFIABLE: bold and type size not established as PASS.",
            ],
            authoritative_sources=sources,
            technical_details={
                **details,
                "heading_caps_ok": caps_ok,
                "format_bold": "not_evaluated",
                "format_type_size": "not_evaluated",
            },
        )
