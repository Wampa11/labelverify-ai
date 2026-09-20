"""
Phase 8.9.1 AI recovery eligibility, visual independence, and reconciliation tests.

Architectural responsibility: regression coverage for OCR_LOW_QUALITY unwrap,
field-aware eligibility, reinforcing OCR+AI merge, and safe failure modes.
Uses scripted providers only — no live OpenAI.
"""

from __future__ import annotations

from app.ai.eligibility import (
    CHECK_TO_FIELD,
    collect_eligible_checks,
    is_eligible_reason,
    underlying_eligible_reason,
)
from app.ai.evidence import AiEvidenceBatchResult, AiEvidenceConfidence, AiFieldEvidence
from app.ai.merge import merge_ai_evidence, validate_field_evidence
from app.ai.null_provider import NullAiProvider
from app.ai.package import PreparedAiImage, build_evidence_package
from app.ai.provider import AiAvailability
from app.core.config import Settings
from app.extraction.retry_policy import merge_conflicts_as_uncertain
from app.models.extraction import ExtractedField, ExtractionMethod, ExtractionStatus
from app.models.verification import (
    CheckStatus,
    DecisionMethod,
    FieldCheckResult,
    ReviewReasonCode,
)
from app.rules.common import extraction_gate
from app.rules.government_warning import GovernmentWarningRule
from app.rules.regulatory_sources import STATUTORY_GOVERNMENT_WARNING
from app.services.verification_service import VerificationService
from tests.image_fixtures import jpeg_bytes


def _check(
    name: str,
    *,
    reason: str,
    eligible: bool = True,
    details: dict | None = None,
    detected: str | None = None,
) -> FieldCheckResult:
    kwargs: dict = {
        "check_name": name,
        "status": CheckStatus.REVIEW,
        "explanation": "t",
        "decision_method": DecisionMethod.HUMAN_REVIEW_REQUIRED,
        "reason_code": reason,
        "ai_assist_eligible": eligible,
        "detected_label_value": detected,
    }
    if details is not None:
        kwargs["technical_details"] = details
    return FieldCheckResult(**kwargs)


def _field(
    name: str,
    status: ExtractionStatus,
    *,
    raw: str | None = None,
    normalized: str | None = None,
    numeric: float | None = None,
    unit: str | None = None,
    explanation: str = "test",
) -> ExtractedField:
    return ExtractedField(
        field_name=name,
        status=status,
        raw_text=raw,
        normalized_value=normalized if normalized is not None else raw,
        normalized_numeric=numeric,
        normalized_unit=unit,
        explanation=explanation,
        extraction_method=ExtractionMethod.REGEX,
    )


# --- A–E eligibility ---------------------------------------------------------


def test_a_warning_not_found_ocr_low_quality_ai_eligible() -> None:
    """A. NOT_FOUND + OCR_LOW_QUALITY warning remains AI-eligible."""
    check = _check(
        "Government Health Warning",
        reason=ReviewReasonCode.OCR_LOW_QUALITY.value,
        eligible=True,
        details={
            "extraction_status": "NOT_FOUND",
            "underlying_reason_code": ReviewReasonCode.WARNING_MISSING.value,
        },
    )
    assert underlying_eligible_reason(check) == ReviewReasonCode.WARNING_MISSING.value
    eligible = collect_eligible_checks([check], overall_status=CheckStatus.REVIEW)
    assert [c.check_name for c in eligible] == ["Government Health Warning"]


def test_b_net_uncertain_ocr_low_quality_ai_eligible() -> None:
    """B. Uncertain/noisy net + OCR_LOW_QUALITY remains AI-eligible."""
    check = _check(
        "Net Contents",
        reason=ReviewReasonCode.OCR_LOW_QUALITY.value,
        eligible=False,  # legacy gate may have cleared the flag
        detected="750 mL (noisy)",
        details={
            "extraction_status": "UNCERTAIN",
            "underlying_reason_code": ReviewReasonCode.EXTRACTION_UNCERTAIN.value,
        },
    )
    assert underlying_eligible_reason(check) == ReviewReasonCode.EXTRACTION_UNCERTAIN.value
    eligible = collect_eligible_checks([check], overall_status=CheckStatus.REVIEW)
    assert [c.check_name for c in eligible] == ["Net Contents"]


def test_c_proof_only_alcohol_ai_eligible() -> None:
    """C. Proof-only alcohol remains AI-eligible."""
    check = _check(
        "Alcohol Content / ABV",
        reason=ReviewReasonCode.PROOF_ONLY_NO_PERCENT_STATEMENT.value,
        detected="90 PROOF",
    )
    assert is_eligible_reason(check.reason_code)
    eligible = collect_eligible_checks([check], overall_status=CheckStatus.REVIEW)
    assert [c.check_name for c in eligible] == ["Alcohol Content / ABV"]


def test_d_formatting_only_not_ai_eligible_despite_quality() -> None:
    """D. Formatting-only / human-only issue does not become AI-eligible."""
    checks = [
        _check(
            "Government Health Warning",
            reason=ReviewReasonCode.FORMAT_NOT_MACHINE_VERIFIABLE.value,
            eligible=False,
            details={
                "quality_status": "WARNING",
                "extraction_status": "FOUND",
            },
        ),
        _check(
            "Brand Name",
            reason=ReviewReasonCode.OCR_LOW_QUALITY.value,
            eligible=False,
            # No underlying extraction state → still ineligible
        ),
    ]
    assert collect_eligible_checks(checks, overall_status=CheckStatus.REVIEW) == []


def test_e_combined_request_contains_all_eligible_unresolved_fields() -> None:
    """E. Combined request includes all eligible unresolved fields."""
    checks = [
        _check(
            "Brand Name",
            reason=ReviewReasonCode.EXTRACTION_UNCERTAIN.value,
            detected="Whispering",
        ),
        _check(
            "Class / Type",
            reason=ReviewReasonCode.EXTRACTION_UNCERTAIN.value,
            detected="BOURBON WHISKEY",
        ),
        _check(
            "Alcohol Content / ABV",
            reason=ReviewReasonCode.PROOF_ONLY_NO_PERCENT_STATEMENT.value,
            detected="(90 PROOF)",
        ),
        _check(
            "Net Contents",
            reason=ReviewReasonCode.OCR_LOW_QUALITY.value,
            details={
                "extraction_status": "UNCERTAIN",
                "underlying_reason_code": "EXTRACTION_UNCERTAIN",
            },
            detected="750 mL",
        ),
        _check(
            "Government Health Warning",
            reason=ReviewReasonCode.OCR_LOW_QUALITY.value,
            details={
                "extraction_status": "NOT_FOUND",
                "underlying_reason_code": "WARNING_MISSING",
            },
        ),
    ]
    eligible = collect_eligible_checks(checks, overall_status=CheckStatus.REVIEW)
    fields = {CHECK_TO_FIELD[c.check_name] for c in eligible}
    assert fields == {
        "brand_name",
        "class_type",
        "alcohol_content",
        "net_contents",
        "government_warning",
    }
    package = build_evidence_package(
        checks=eligible,
        fields={},
        quality_status="WARNING",
        quality_warnings=["blur"],
    )
    assert {item.field for item in package.fields} == fields
    by_field = {item.field: item.reason_code for item in package.fields}
    assert by_field["net_contents"] == "EXTRACTION_UNCERTAIN"
    assert by_field["government_warning"] == "WARNING_MISSING"


# --- F–I merge / visual recovery semantics -----------------------------------


def test_f_ocr_proof_only_ai_recovers_abv_and_proof() -> None:
    """F. OCR proof-only + AI visually recovers ABV + proof."""
    fields = {
        "alcohol_content": _field(
            "alcohol_content",
            ExtractionStatus.FOUND,
            raw="(90 PROOF)",
            normalized="proof=90",
            numeric=45.0,
            unit="%",
            explanation="Proof recovered without percentage ABV statement.",
        ),
    }
    batch = AiEvidenceBatchResult(
        availability="available",
        provider_name="scripted",
        fields=[
            AiFieldEvidence(
                field="alcohol_content",
                candidate_value="45% ALC./VOL. (90 PROOF)",
                raw_observed_text="45% ALC./VOL. (90 PROOF)",
                confidence=AiEvidenceConfidence.HIGH,
                evidence_description="Both ABV and proof visible on image",
            ),
        ],
        explanation="ok",
        called=True,
    )
    merged, updated, conflicts, outcomes = merge_ai_evidence(fields, batch)
    assert conflicts == []
    assert updated == ["alcohol_content"]
    assert outcomes["alcohol_content"] == "supplemented"
    assert merged["alcohol_content"].status == ExtractionStatus.FOUND
    assert merged["alcohol_content"].normalized_numeric == 45.0
    assert "45" in (merged["alcohol_content"].normalized_value or "")


def test_g_ai_must_not_invent_abv_from_proof_only_candidate() -> None:
    """G. Proof-only AI candidate without parseable ABV is rejected."""
    ok, reason = validate_field_evidence(
        AiFieldEvidence(
            field="alcohol_content",
            candidate_value="(90 PROOF)",
            confidence=AiEvidenceConfidence.HIGH,
            unable_to_determine=False,
        ),
    )
    assert ok is False
    assert reason == "abv_unparseable"


def test_h_noisy_ocr_net_ai_750ml_reconciles() -> None:
    """H. Noisy OCR net + AI 750 mL reconciles correctly."""
    fields = {
        "net_contents": _field(
            "net_contents",
            ExtractionStatus.UNCERTAIN,
            raw="75O mL 90 PROOF",
            normalized="750 mL",
            numeric=750.0,
            unit="mL",
        ),
    }
    batch = AiEvidenceBatchResult(
        availability="available",
        provider_name="scripted",
        fields=[
            AiFieldEvidence(
                field="net_contents",
                candidate_value="750 mL",
                confidence=AiEvidenceConfidence.HIGH,
                evidence_description="Visible net contents",
            ),
        ],
        explanation="ok",
        called=True,
    )
    merged, updated, conflicts, outcomes = merge_ai_evidence(fields, batch)
    assert conflicts == []
    assert outcomes["net_contents"] == "filled"
    assert merged["net_contents"].status == ExtractionStatus.FOUND
    assert merged["net_contents"].normalized_value == "750 mL"
    assert merged["net_contents"].normalized_numeric == 750.0


def test_i_missing_ocr_warning_ai_transcription_enters_validation() -> None:
    """I. Missing OCR warning + AI transcription enters deterministic warning path."""
    from app.models.verification import ApplicationData
    from app.models.verification_mode import VerificationMode
    from app.rules.base import RuleContext

    fields = {
        "government_warning": _field(
            "government_warning",
            ExtractionStatus.NOT_FOUND,
            explanation="No header",
        ),
    }
    batch = AiEvidenceBatchResult(
        availability="available",
        provider_name="scripted",
        fields=[
            AiFieldEvidence(
                field="government_warning",
                candidate_value=STATUTORY_GOVERNMENT_WARNING[:100],
                raw_observed_text=STATUTORY_GOVERNMENT_WARNING,
                confidence=AiEvidenceConfidence.HIGH,
                evidence_description="Warning block visible",
            ),
        ],
        explanation="ok",
        called=True,
    )
    merged, _updated, conflicts, _outcomes = merge_ai_evidence(fields, batch)
    assert conflicts == []
    assert merged["government_warning"].status == ExtractionStatus.FOUND
    assert merged["government_warning"].raw_text
    assert "GOVERNMENT WARNING" in (merged["government_warning"].raw_text or "").upper()

    result = GovernmentWarningRule().evaluate(
        RuleContext(
            application=ApplicationData(
                brand_name="X",
                class_type="Y",
                alcohol_content_abv="40%",
                net_contents="750 mL",
            ),
            fields=merged,
            quality_status="GOOD",
            mode=VerificationMode.LABEL_ONLY,
        ),
    )
    assert result.reason_code != ReviewReasonCode.WARNING_MISSING.value
    assert result.detected_label_value


# --- J–L reconciliation / safety ---------------------------------------------


def test_j_strong_fast_class_plus_agreeing_ai_becomes_found() -> None:
    """J. Strong FAST class/type + agreeing AI → FOUND despite noisy enhanced OCR."""
    selected = {
        "class_type": _field(
            "class_type",
            ExtractionStatus.FOUND,
            raw="BOURBON WHISKEY",
            normalized="BOURBON WHISKEY",
            explanation="FAST OCR terminology match",
        ),
    }
    other = {
        "class_type": _field(
            "class_type",
            ExtractionStatus.FOUND,
            raw="di BOURBON WHISKEY",
            normalized="di BOURBON WHISKEY",
            explanation="noisy enhanced",
        ),
    }
    after_conflict = merge_conflicts_as_uncertain(selected, other)
    assert after_conflict["class_type"].status == ExtractionStatus.FOUND
    assert "BOURBON WHISKEY" in (
        after_conflict["class_type"].normalized_value or ""
    ).upper()
    assert "di" not in (after_conflict["class_type"].normalized_value or "").casefold()

    # Even if somehow UNCERTAIN, agreeing MEDIUM AI reinforces to FOUND
    uncertain = after_conflict["class_type"].model_copy(
        update={"status": ExtractionStatus.UNCERTAIN},
    )
    batch = AiEvidenceBatchResult(
        availability="available",
        provider_name="scripted",
        fields=[
            AiFieldEvidence(
                field="class_type",
                candidate_value="BOURBON WHISKEY",
                confidence=AiEvidenceConfidence.MEDIUM,
                evidence_description="Class line visible",
            ),
        ],
        explanation="ok",
        called=True,
    )
    merged, _updated, conflicts, outcomes = merge_ai_evidence(
        {"class_type": uncertain},
        batch,
    )
    assert conflicts == []
    assert outcomes["class_type"] == "filled"
    assert merged["class_type"].status == ExtractionStatus.FOUND


def test_k_ocr_ai_disagreement_remains_uncertain() -> None:
    """K. OCR/AI disagreement remains UNCERTAIN."""
    fields = {
        "class_type": _field(
            "class_type",
            ExtractionStatus.FOUND,
            raw="VODKA",
            normalized="VODKA",
        ),
    }
    batch = AiEvidenceBatchResult(
        availability="available",
        provider_name="scripted",
        fields=[
            AiFieldEvidence(
                field="class_type",
                candidate_value="BOURBON WHISKEY",
                confidence=AiEvidenceConfidence.HIGH,
                evidence_description="conflict",
            ),
        ],
        explanation="ok",
        called=True,
    )
    merged, _updated, conflicts, outcomes = merge_ai_evidence(fields, batch)
    assert conflicts
    assert outcomes["class_type"] == "conflict"
    assert merged["class_type"].status == ExtractionStatus.UNCERTAIN


def test_l_unable_to_determine_rejected() -> None:
    """L. unable_to_determine=true remains rejected."""
    ok, reason = validate_field_evidence(
        AiFieldEvidence(
            field="brand_name",
            candidate_value="Whispering Pine",
            confidence=AiEvidenceConfidence.HIGH,
            unable_to_determine=True,
        ),
    )
    assert ok is False and reason == "unable_to_determine"
    fields = {
        "brand_name": _field(
            "brand_name",
            ExtractionStatus.UNCERTAIN,
            raw="ie DISTILLERY",
        ),
    }
    batch = AiEvidenceBatchResult(
        availability="available",
        provider_name="scripted",
        fields=[
            AiFieldEvidence(
                field="brand_name",
                candidate_value="Whispering Pine",
                confidence=AiEvidenceConfidence.HIGH,
                unable_to_determine=True,
            ),
        ],
        explanation="ok",
        called=True,
    )
    merged, updated, _conflicts, outcomes = merge_ai_evidence(fields, batch)
    assert updated == []
    assert outcomes["brand_name"] == "rejected:unable_to_determine"
    assert merged["brand_name"].status == ExtractionStatus.UNCERTAIN


# --- M–N provider failure / disabled -----------------------------------------


def test_m_ai_provider_failure_safe_review() -> None:
    """M. AI provider failure remains safe REVIEW."""
    from app.ai.evidence import AiEvidencePackage
    from app.ai.openai_provider import OpenAiProvider

    provider = OpenAiProvider(api_key="sk-test", model="gpt-4o-mini", timeout_seconds=0.01)
    # Force failure via unreachable base URL
    provider._base_url = "http://127.0.0.1:9"
    batch = provider.recover_label_evidence(
        AiEvidencePackage(fields=[]),
        PreparedAiImage(image_bytes=b"\xff\xd8\xff\xd9", width_px=1, height_px=1),
    )
    assert batch.fields == []
    assert batch.called is True
    assert "REVIEW" in (batch.explanation or "").upper() or batch.availability != "available"


def test_n_disabled_ai_safe_review() -> None:
    """N. Disabled AI remains safe REVIEW."""
    from app.ai.evidence import AiEvidencePackage
    from app.models.verification import ApplicationData
    from tests.test_ai_fallback import ScriptedOcrProvider

    provider = NullAiProvider()
    assert provider.availability() == AiAvailability.DISABLED
    batch = provider.recover_label_evidence(
        AiEvidencePackage(fields=[]),
        PreparedAiImage(image_bytes=b"\xff\xd8\xff\xd9", width_px=1, height_px=1),
    )
    assert batch.called is False
    assert batch.fields == []

    service = VerificationService(
        ocr_provider=ScriptedOcrProvider("incomplete label text only"),
        ai_provider=provider,
        settings=Settings(openai_enabled=False),
    )
    result = service.verify(
        jpeg_bytes(),
        ApplicationData(
            brand_name="X",
            class_type="Y",
            alcohol_content_abv="40%",
            net_contents="750 mL",
        ),
    )
    assert result.verification.overall_status == CheckStatus.REVIEW
    assert result.verification.ai_assist["ai_configured"] is False
    assert result.verification.ai_used is False


def test_extraction_gate_preserves_underlying_reason_under_quality() -> None:
    """Gate keeps AI eligibility when display reason becomes OCR_LOW_QUALITY."""
    field = _field("net_contents", ExtractionStatus.NOT_FOUND, explanation="missed")
    gated = extraction_gate(
        rule_id="RULE-TEST",
        check_name="Net Contents",
        application_value=None,
        field=field,
        sources=["test"],
        quality_status="WARNING",
    )
    assert gated is not None
    assert gated.reason_code == ReviewReasonCode.OCR_LOW_QUALITY.value
    assert gated.ai_assist_eligible is True
    assert gated.technical_details["underlying_reason_code"] == (
        ReviewReasonCode.EXTRACTION_NOT_FOUND.value
    )
    assert underlying_eligible_reason(gated) == ReviewReasonCode.EXTRACTION_NOT_FOUND.value
