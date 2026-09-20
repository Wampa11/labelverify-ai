"""
Phase 8.7 extraction integrity regressions.

Architectural responsibility: failure-mode coverage for structured parsing, brand
scoring, confidence gating, and OCR↔AI reconciliation — not fixture-name hacks.
"""

from __future__ import annotations

from app.ai.eligibility import collect_eligible_checks, is_eligible_reason
from app.ai.evidence import AiEvidenceBatchResult, AiEvidenceConfidence, AiFieldEvidence
from app.ai.merge import merge_ai_evidence
from app.ai.null_provider import NullAiProvider
from app.extraction.alcohol_content import extract_alcohol_content
from app.extraction.brand_name import extract_brand_name
from app.extraction.class_type import extract_class_type
from app.extraction.government_warning import extract_government_warning
from app.extraction.net_contents import extract_net_contents
from app.models.extraction import ExtractedField, ExtractionMethod, ExtractionStatus
from app.models.verification import CheckStatus, DecisionMethod, FieldCheckResult
from app.normalization.field_parsers import (
    net_contents_evidence_is_reliable,
    parse_alcohol_content,
    parse_net_contents,
)
from app.ocr.base import OcrResult, OcrWord
from app.rules.regulatory_sources import STATUTORY_GOVERNMENT_WARNING


def _ocr(
    text: str,
    *,
    words: list[OcrWord] | None = None,
    width: int = 800,
    height: int = 600,
) -> OcrResult:
    return OcrResult(
        full_text=text,
        words=words or [],
        provider_name="test",
        image_width_px=width,
        image_height_px=height,
        preprocessing_profile="fast",
    )


def _word(
    text: str,
    *,
    conf: float = 0.92,
    x0: float = 40,
    y0: float = 30,
    x1: float = 120,
    y1: float = 70,
) -> OcrWord:
    return OcrWord(
        text=text,
        confidence=conf,
        bounding_box={"x_min": x0, "y_min": y0, "x_max": x1, "y_max": y1},
    )


# A. Clean prominent two-word brand
def test_a_clean_two_word_brand_preferred() -> None:
    text = "RIVER BEND\nDISTILLERY\nStraight Bourbon Whiskey\n45% Alc./Vol.\n750 mL"
    words = [
        _word("RIVER", x0=80, y0=20, x1=200, y1=70),
        _word("BEND", x0=210, y0=20, x1=320, y1=70),
        _word("DISTILLERY", conf=0.9, x0=100, y0=90, x1=280, y1=120),
    ]
    field = extract_brand_name(_ocr(text, words=words))
    assert field.status == ExtractionStatus.FOUND
    assert field.normalized_value == "RIVER BEND"


# B. Isolated DISTILLERY competing with a real brand
def test_b_isolated_distillery_loses_to_brand() -> None:
    text = "CEDAR HILLS\nDISTILLERY\n45% Alc./Vol.\n750 mL"
    words = [
        _word("CEDAR", x0=60, y0=15, x1=180, y1=65),
        _word("HILLS", x0=190, y0=15, x1=300, y1=65),
        _word("DISTILLERY", conf=0.95, x0=90, y0=100, x1=260, y1=130),
    ]
    field = extract_brand_name(_ocr(text, words=words))
    assert field.status == ExtractionStatus.FOUND
    assert "CEDAR" in (field.normalized_value or "")
    assert field.normalized_value != "DISTILLERY"


# C. Isolated DISTILLING CO. competing with a real brand
def test_c_isolated_distilling_co_penalized() -> None:
    text = "IRON RIDGE\nDISTILLING CO.\nRye Whiskey\n40% Alc./Vol.\n750 mL"
    words = [
        _word("IRON", x0=50, y0=10, x1=140, y1=60),
        _word("RIDGE", x0=150, y0=10, x1=260, y1=60),
        _word("DISTILLING", conf=0.9, x0=80, y0=95, x1=220, y1=125),
        _word("CO.", conf=0.9, x0=225, y0=95, x1=270, y1=125),
    ]
    field = extract_brand_name(_ocr(text, words=words))
    assert field.status == ExtractionStatus.FOUND
    assert field.normalized_value == "IRON RIDGE"


# D. Partial/clipped first character in brand OCR
def test_d_clipped_leading_brand_is_uncertain() -> None:
    text = "APPLE CREEK\nBourbon Whiskey\n40% Alc./Vol.\n750 mL"
    words = [
        _word("APPLE", conf=0.28, x0=1, y0=20, x1=110, y1=70),
        _word("CREEK", conf=0.9, x0=120, y0=20, x1=240, y1=70),
    ]
    field = extract_brand_name(_ocr(text, words=words, width=800))
    assert field.status == ExtractionStatus.UNCERTAIN
    assert "APPLE" in (field.raw_text or "")


def test_d2_malformed_brand_trailing_equals_uncertain() -> None:
    text = "hispering =\nBourbon Whiskey\n40% Alc./Vol.\n750 mL"
    words = [
        _word("hispering", conf=0.7, x0=40, y0=20, x1=180, y1=60),
        _word("=", conf=0.4, x0=185, y0=25, x1=200, y1=55),
    ]
    field = extract_brand_name(_ocr(text, words=words))
    assert field.status == ExtractionStatus.UNCERTAIN


def test_d3_left_orphan_fragment_marks_uncertain() -> None:
    """Independent adjacent fragment suggests truncation without inventing letters."""
    text = "APLE CREEK\nBourbon Whiskey\n40% Alc./Vol.\n750 mL"
    words = [
        OcrWord(
            text="M",
            confidence=0.6,
            bounding_box={"x_min": 20, "y_min": 22, "x_max": 35, "y_max": 68},
        ),
        _word("APLE", conf=0.9, x0=40, y0=20, x1=130, y1=70),
        _word("CREEK", conf=0.9, x0=140, y0=20, x1=250, y1=70),
    ]
    field = extract_brand_name(_ocr(text, words=words))
    assert field.status == ExtractionStatus.UNCERTAIN


# E. "(90 PROOF) 750 mL" structured parsing
def test_e_proof_does_not_contaminate_net_normalized() -> None:
    line = "(90 PROOF) 750 mL"
    parsed = parse_net_contents(line)
    assert parsed is not None
    assert parsed.value == 750.0
    assert parsed.unit == "mL"
    assert parsed.raw_text == "750 mL"
    assert "proof" not in parsed.raw_text.lower()
    assert net_contents_evidence_is_reliable(line, parsed)

    field = extract_net_contents(_ocr(f"Brand\n{line}\nGOVERNMENT WARNING"))
    assert field.normalized_value == "750 mL"
    assert field.raw_text == line
    assert field.status == ExtractionStatus.FOUND


# F. Noisy prefix + "750mL"
def test_f_noisy_prefix_net_is_uncertain() -> None:
    line = "ge | 750mL"
    parsed = parse_net_contents(line)
    assert parsed is not None
    assert parsed.raw_text == "750 mL"
    assert not net_contents_evidence_is_reliable(line, parsed)

    field = extract_net_contents(_ocr(line))
    assert field.normalized_value == "750 mL"
    assert field.status == ExtractionStatus.UNCERTAIN


# G. Proof recovered but ABV missing
def test_g_proof_only_not_treated_as_abv_statement() -> None:
    parsed = parse_alcohol_content("90 PROOF")
    assert parsed is not None
    assert parsed.source == "proof"
    assert parsed.abv_percent == 45.0

    field = extract_alcohol_content(_ocr("Brand\n90 PROOF\n750 mL"))
    assert field.status == ExtractionStatus.FOUND
    assert field.normalized_numeric == 45.0
    # Rules: proof-only → REVIEW in label-only mode
    from app.rules.base import RuleContext
    from app.rules.label_evidence import LabelFieldEvidenceRule

    rule = LabelFieldEvidenceRule(
        rule_id="t",
        check_name="Alcohol Content / ABV",
        field_key="alcohol_content",
        source_keys=("cfr_5_65",),
    )
    result = rule.evaluate(
        RuleContext(application=None, fields={"alcohol_content": field}, quality_status="GOOD"),
    )
    assert result.status == CheckStatus.REVIEW
    assert result.reason_code == "PROOF_ONLY_NO_PERCENT_STATEMENT"
    assert is_eligible_reason(result.reason_code)


# H. Partial class/type evidence
def test_h_partial_class_type_uncertain() -> None:
    field = extract_class_type(_ocr("KENTUCKY STRAIGHT BOURBON WHIS..."))
    assert field.status == ExtractionStatus.UNCERTAIN
    assert "BOURBON" in (field.raw_text or "").upper()


# I. OCR + AI mutually reinforcing evidence
def test_i_ocr_proof_ai_abv_reinforcing() -> None:
    fields = {
        "alcohol_content": ExtractedField(
            field_name="alcohol_content",
            status=ExtractionStatus.FOUND,
            raw_text="90 PROOF",
            normalized_value="proof=90",
            normalized_numeric=45.0,
            normalized_unit="%",
            explanation=(
                "Proof was recovered without a clear percentage alcohol-by-volume statement."
            ),
            extraction_method=ExtractionMethod.REGEX,
            ai_fallback_hints={"source": "proof"},
        ),
    }
    batch = AiEvidenceBatchResult(
        availability="available",
        provider_name="scripted",
        fields=[
            AiFieldEvidence(
                field="alcohol_content",
                candidate_value="45% ALC./VOL. (90 PROOF)",
                confidence=AiEvidenceConfidence.HIGH,
                evidence_description="Visible ABV with proof",
            ),
        ],
        explanation="ok",
        called=True,
    )
    merged, updated, conflicts, _outcomes = merge_ai_evidence(fields, batch)
    assert conflicts == []
    assert updated == ["alcohol_content"]
    assert merged["alcohol_content"].status == ExtractionStatus.FOUND
    assert merged["alcohol_content"].normalized_numeric == 45.0
    assert "45" in (merged["alcohol_content"].normalized_value or "")


def test_i_partial_class_ai_reinforcing() -> None:
    fields = {
        "class_type": ExtractedField(
            field_name="class_type",
            status=ExtractionStatus.UNCERTAIN,
            raw_text="BOURBON WHIS...",
            normalized_value="BOURBON WHIS...",
            explanation="partial",
            extraction_method=ExtractionMethod.TERMINOLOGY_MATCH,
        ),
    }
    batch = AiEvidenceBatchResult(
        availability="available",
        provider_name="scripted",
        fields=[
            AiFieldEvidence(
                field="class_type",
                candidate_value="KENTUCKY STRAIGHT BOURBON WHISKEY",
                confidence=AiEvidenceConfidence.HIGH,
                evidence_description="Full class line",
            ),
        ],
        explanation="ok",
        called=True,
    )
    merged, updated, conflicts, _outcomes = merge_ai_evidence(fields, batch)
    assert conflicts == []
    assert merged["class_type"].status == ExtractionStatus.FOUND
    assert "KENTUCKY" in (merged["class_type"].normalized_value or "")


# J. OCR + AI conflicting evidence
def test_j_ocr_ai_conflict_uncertain() -> None:
    fields = {
        "brand_name": ExtractedField(
            field_name="brand_name",
            status=ExtractionStatus.FOUND,
            raw_text="CEDAR HILLS",
            normalized_value="CEDAR HILLS",
            explanation="ok",
            extraction_method=ExtractionMethod.LAYOUT_HEURISTIC,
        ),
    }
    batch = AiEvidenceBatchResult(
        availability="available",
        provider_name="scripted",
        fields=[
            AiFieldEvidence(
                field="brand_name",
                candidate_value="IRON RIDGE",
                confidence=AiEvidenceConfidence.HIGH,
                evidence_description="conflict",
            ),
        ],
        explanation="ok",
        called=True,
    )
    merged, updated, conflicts, _outcomes = merge_ai_evidence(fields, batch)
    assert conflicts
    assert merged["brand_name"].status == ExtractionStatus.UNCERTAIN
    assert "CONFLICTING_EVIDENCE" in merged["brand_name"].explanation


# K. Warning recovered only through fallback
def test_k_warning_recovered_via_ai_fallback() -> None:
    fields = {
        "government_warning": ExtractedField(
            field_name="government_warning",
            status=ExtractionStatus.NOT_FOUND,
            explanation="No header",
            extraction_method=ExtractionMethod.NOT_EXTRACTED,
            ai_fallback_hints={"reason": "warning_header_missing"},
        ),
    }
    batch = AiEvidenceBatchResult(
        availability="available",
        provider_name="scripted",
        fields=[
            AiFieldEvidence(
                field="government_warning",
                candidate_value=STATUTORY_GOVERNMENT_WARNING[:80],
                raw_observed_text=STATUTORY_GOVERNMENT_WARNING,
                confidence=AiEvidenceConfidence.HIGH,
                evidence_description="Warning block visible",
            ),
        ],
        explanation="ok",
        called=True,
    )
    merged, updated, conflicts, _outcomes = merge_ai_evidence(fields, batch)
    assert conflicts == []
    assert merged["government_warning"].status == ExtractionStatus.FOUND
    assert merged["government_warning"].normalized_value == "GOVERNMENT WARNING"

    # Eligibility: missing warning REVIEW is AI-eligible
    assert is_eligible_reason("WARNING_MISSING")
    assert is_eligible_reason("EXTRACTION_NOT_FOUND")
    checks = [
        FieldCheckResult(
            check_name="Government Health Warning",
            status=CheckStatus.REVIEW,
            explanation="missing",
            decision_method=DecisionMethod.HUMAN_REVIEW_REQUIRED,
            reason_code="WARNING_MISSING",
            ai_assist_eligible=True,
        ),
    ]
    eligible = collect_eligible_checks(checks, overall_status=CheckStatus.REVIEW)
    assert len(eligible) == 1


# L. OpenAI unavailable leaves safe REVIEW behavior
def test_l_openai_unavailable_safe_review() -> None:
    from app.ai.evidence import AiEvidencePackage
    from app.ai.package import PreparedAiImage
    from app.ai.provider import AiAvailability
    from app.models.verification_mode import VerificationMode
    from app.rules.base import RuleContext
    from app.rules.engine import aggregate_overall_status, run_rules

    provider = NullAiProvider()
    assert provider.availability() == AiAvailability.DISABLED
    batch = provider.recover_label_evidence(
        AiEvidencePackage(fields=[]),
        PreparedAiImage(image_bytes=b"\xff\xd8\xff", width_px=1, height_px=1),
    )
    assert batch.called is False
    assert batch.fields == []

    # Noisy net → UNCERTAIN → REVIEW without needing AI
    fields = {
        "brand_name": ExtractedField(
            field_name="brand_name",
            status=ExtractionStatus.FOUND,
            raw_text="RIVER BEND",
            normalized_value="RIVER BEND",
            explanation="ok",
            extraction_method=ExtractionMethod.LAYOUT_HEURISTIC,
        ),
        "class_type": ExtractedField(
            field_name="class_type",
            status=ExtractionStatus.FOUND,
            raw_text="Straight Bourbon Whiskey",
            normalized_value="Straight Bourbon Whiskey",
            explanation="ok",
            extraction_method=ExtractionMethod.TERMINOLOGY_MATCH,
        ),
        "alcohol_content": ExtractedField(
            field_name="alcohol_content",
            status=ExtractionStatus.FOUND,
            raw_text="45% Alc./Vol.",
            normalized_value="45% Alc./Vol.",
            normalized_numeric=45.0,
            normalized_unit="%",
            explanation="ok",
            extraction_method=ExtractionMethod.REGEX,
        ),
        "net_contents": extract_net_contents(_ocr("ge | 750mL")),
        "government_warning": extract_government_warning(
            _ocr(STATUTORY_GOVERNMENT_WARNING),
        ),
    }
    assert fields["net_contents"].status == ExtractionStatus.UNCERTAIN
    checks = run_rules(
        RuleContext(
            application=None,
            fields=fields,
            quality_status="GOOD",
            mode=VerificationMode.LABEL_ONLY,
        ),
    )
    net_check = next(c for c in checks if c.check_name == "Net Contents")
    assert net_check.status == CheckStatus.REVIEW
    assert aggregate_overall_status(checks) == CheckStatus.REVIEW
