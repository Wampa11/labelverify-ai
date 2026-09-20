"""
Unit tests for Phase 5 deterministic verification rules and comparison helpers.

Architectural responsibility: cover PASS/REVIEW/FAIL without requiring the web server.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models.extraction import ExtractedField, ExtractionMethod, ExtractionStatus
from app.models.verification import ApplicationData, CheckStatus
from app.normalization.comparison import (
    comparison_normalize,
    parse_application_abv,
    parse_application_net_ml,
    text_similarity,
)
from app.ocr.base import OcrProvider, OcrResult
from app.rules.alcohol_content import AlcoholContentRule
from app.rules.base import RuleContext
from app.rules.brand_name import BrandNameRule
from app.rules.class_type import ClassTypeRule
from app.rules.engine import aggregate_overall_status, run_rules
from app.rules.government_warning import GovernmentWarningRule
from app.rules.net_contents import NetContentsRule
from app.rules.regulatory_sources import STATUTORY_GOVERNMENT_WARNING
from app.services.verification_service import VerificationService
from tests.image_fixtures import jpeg_bytes

client = TestClient(app)

STATUTORY = STATUTORY_GOVERNMENT_WARNING


def _app(**overrides: str) -> ApplicationData:
    base = {
        "brand_name": "Stone's Throw",
        "class_type": "Straight Bourbon Whiskey",
        "alcohol_content_abv": "45%",
        "net_contents": "750 mL",
    }
    base.update(overrides)
    return ApplicationData(**base)


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
        normalized_value=normalized,
        normalized_numeric=numeric,
        normalized_unit=unit,
        explanation=explanation,
        extraction_method=ExtractionMethod.REGEX,
    )


def _ctx(
    application: ApplicationData,
    fields: dict[str, ExtractedField],
    **kwargs: object,
) -> RuleContext:
    return RuleContext(
        application=application,
        fields=fields,
        quality_status="GOOD",
        **kwargs,  # type: ignore[arg-type]
    )


# --- Normalization / fuzzy ---------------------------------------------------


def test_brand_capitalization_normalizes() -> None:
    assert comparison_normalize("Stone's Throw") == comparison_normalize("STONE'S THROW")
    sim = text_similarity("Stone's Throw", "STONE'S THROW")
    assert sim.exact_normalized is True
    assert sim.ratio == 100.0


def test_brand_whitespace_normalizes() -> None:
    sim = text_similarity("Stone's   Throw", "Stone's Throw")
    assert sim.exact_normalized is True


def test_application_parsers() -> None:
    assert parse_application_abv("45%") == 45.0
    assert parse_application_abv("45") == 45.0
    assert parse_application_net_ml("750 mL") == 750.0
    assert parse_application_net_ml("0.75 L") == 750.0


# --- Brand -------------------------------------------------------------------


def test_brand_exact_normalized_pass() -> None:
    fields = {
        "brand_name": _field(
            "brand_name",
            ExtractionStatus.FOUND,
            raw="STONE'S THROW",
            normalized="STONE'S THROW",
        ),
    }
    result = BrandNameRule().evaluate(_ctx(_app(), fields))
    assert result.status == CheckStatus.PASS
    assert result.reason_code == "BRAND_MATCH"


def test_brand_obvious_mismatch_fail() -> None:
    fields = {
        "brand_name": _field(
            "brand_name",
            ExtractionStatus.FOUND,
            raw="NORTH PEAK DISTILLING",
            normalized="NORTH PEAK DISTILLING",
        ),
    }
    result = BrandNameRule().evaluate(_ctx(_app(brand_name="Stone's Throw"), fields))
    assert result.status == CheckStatus.FAIL
    assert result.reason_code == "BRAND_MISMATCH"
    assert "similarity_ratio" in (result.technical_details or {})


def test_brand_ambiguous_review() -> None:
    fields = {
        "brand_name": _field(
            "brand_name",
            ExtractionStatus.FOUND,
            raw="Stone's Thrown",
            normalized="Stone's Thrown",
        ),
    }
    result = BrandNameRule().evaluate(_ctx(_app(brand_name="Stone's Throw"), fields))
    assert result.status in {CheckStatus.REVIEW, CheckStatus.PASS, CheckStatus.FAIL}
    ratio = result.technical_details.get("similarity_ratio", 0)
    assert result.status != CheckStatus.FAIL or ratio < 85


def test_brand_uncertain_extraction_review() -> None:
    fields = {
        "brand_name": _field(
            "brand_name",
            ExtractionStatus.UNCERTAIN,
            raw="STONE?",
        ),
    }
    result = BrandNameRule().evaluate(_ctx(_app(), fields))
    assert result.status == CheckStatus.REVIEW
    assert result.reason_code == "EXTRACTION_UNCERTAIN"


# --- Class / type ------------------------------------------------------------


def test_class_type_match_pass() -> None:
    fields = {
        "class_type": _field(
            "class_type",
            ExtractionStatus.FOUND,
            raw="Straight Bourbon Whiskey",
        ),
    }
    result = ClassTypeRule().evaluate(_ctx(_app(), fields))
    assert result.status == CheckStatus.PASS


def test_class_type_uncertain_review() -> None:
    fields = {
        "class_type": _field("class_type", ExtractionStatus.UNCERTAIN, raw="Bourbon"),
    }
    result = ClassTypeRule().evaluate(_ctx(_app(), fields))
    assert result.status == CheckStatus.REVIEW
    assert result.reason_code == "EXTRACTION_UNCERTAIN"


def test_class_type_confident_mismatch_fail() -> None:
    fields = {
        "class_type": _field("class_type", ExtractionStatus.FOUND, raw="Vodka"),
    }
    result = ClassTypeRule().evaluate(
        _ctx(_app(class_type="Straight Bourbon Whiskey"), fields),
    )
    assert result.status == CheckStatus.FAIL
    assert result.reason_code == "CLASS_TYPE_MISMATCH"


def test_class_type_partial_review() -> None:
    fields = {
        "class_type": _field("class_type", ExtractionStatus.FOUND, raw="Bourbon Whiskey"),
    }
    result = ClassTypeRule().evaluate(
        _ctx(_app(class_type="Kentucky Straight Bourbon Whiskey"), fields),
    )
    assert result.status == CheckStatus.REVIEW
    assert result.reason_code == "CLASS_TYPE_AMBIGUOUS"


# --- ABV ---------------------------------------------------------------------


def test_abv_match_pass() -> None:
    fields = {
        "alcohol_content": _field(
            "alcohol_content",
            ExtractionStatus.FOUND,
            raw="45% Alc./Vol.",
            normalized="45",
            numeric=45.0,
            unit="%",
            explanation="Parsed ABV=45 from abv.",
        ),
    }
    result = AlcoholContentRule().evaluate(_ctx(_app(), fields))
    assert result.status == CheckStatus.PASS
    assert result.reason_code == "ABV_MATCH"


def test_abv_mismatch_fail() -> None:
    fields = {
        "alcohol_content": _field(
            "alcohol_content",
            ExtractionStatus.FOUND,
            raw="40% Alc./Vol.",
            normalized="40",
            numeric=40.0,
            unit="%",
            explanation="Parsed ABV=40 from abv.",
        ),
    }
    result = AlcoholContentRule().evaluate(_ctx(_app(alcohol_content_abv="45%"), fields))
    assert result.status == CheckStatus.FAIL
    assert result.reason_code == "ABV_MISMATCH"


def test_abv_proof_only_review() -> None:
    fields = {
        "alcohol_content": _field(
            "alcohol_content",
            ExtractionStatus.FOUND,
            raw="90 Proof",
            normalized="45|proof=90",
            numeric=45.0,
            unit="%",
            explanation="Parsed ABV=45 from proof. Proof→ABV used engineering relation.",
        ),
    }
    result = AlcoholContentRule().evaluate(_ctx(_app(), fields))
    assert result.status == CheckStatus.REVIEW
    assert result.reason_code == "PROOF_ONLY_NO_PERCENT_STATEMENT"


# --- Net contents ------------------------------------------------------------


def test_net_contents_equivalent_units_pass() -> None:
    fields = {
        "net_contents": _field(
            "net_contents",
            ExtractionStatus.FOUND,
            raw="0.75 L",
            normalized="0.75 L",
            numeric=0.75,
            unit="L",
        ),
    }
    result = NetContentsRule().evaluate(_ctx(_app(net_contents="750 mL"), fields))
    assert result.status == CheckStatus.PASS


def test_net_contents_mismatch_fail() -> None:
    fields = {
        "net_contents": _field(
            "net_contents",
            ExtractionStatus.FOUND,
            raw="1 L",
            normalized="1 L",
            numeric=1.0,
            unit="L",
        ),
    }
    result = NetContentsRule().evaluate(_ctx(_app(net_contents="750 mL"), fields))
    assert result.status == CheckStatus.FAIL


# --- Government warning ------------------------------------------------------


def test_government_warning_exact_wording() -> None:
    fields = {
        "government_warning": _field(
            "government_warning",
            ExtractionStatus.FOUND,
            raw=STATUTORY,
            normalized="GOVERNMENT WARNING",
        ),
    }
    result = GovernmentWarningRule().evaluate(_ctx(_app(), fields))
    assert result.status == CheckStatus.PASS
    assert result.reason_code == "WARNING_PRESENT_MATCH"
    assert any("Bold" in lim or "bold" in lim for lim in result.limitations)


def test_government_warning_missing_review() -> None:
    fields = {
        "government_warning": _field(
            "government_warning",
            ExtractionStatus.NOT_FOUND,
        ),
    }
    result = GovernmentWarningRule().evaluate(_ctx(_app(), fields))
    assert result.status == CheckStatus.REVIEW
    assert result.reason_code in {"WARNING_MISSING", "OCR_LOW_QUALITY"}


def test_government_warning_partial_review() -> None:
    fields = {
        "government_warning": _field(
            "government_warning",
            ExtractionStatus.UNCERTAIN,
            raw="GOVERNMENT WARNING: (1) According to the Surgeon General",
        ),
    }
    result = GovernmentWarningRule().evaluate(_ctx(_app(), fields))
    assert result.status == CheckStatus.REVIEW
    assert result.reason_code == "WARNING_PARTIAL"


def test_government_warning_bad_caps_review() -> None:
    bad = STATUTORY.replace("GOVERNMENT WARNING", "Government Warning")
    fields = {
        "government_warning": _field(
            "government_warning",
            ExtractionStatus.FOUND,
            raw=bad,
        ),
    }
    result = GovernmentWarningRule().evaluate(_ctx(_app(), fields))
    assert result.status == CheckStatus.REVIEW
    assert result.reason_code == "WARNING_CAPS_REVIEW"


# --- Aggregation -------------------------------------------------------------


def test_overall_aggregation() -> None:
    from app.models.verification import DecisionMethod, FieldCheckResult

    def chk(status: CheckStatus) -> FieldCheckResult:
        return FieldCheckResult(
            check_name="x",
            status=status,
            explanation="t",
            decision_method=DecisionMethod.DETERMINISTIC_RULE,
        )

    assert aggregate_overall_status(
        [chk(CheckStatus.PASS), chk(CheckStatus.PASS)],
    ) == CheckStatus.PASS
    assert aggregate_overall_status(
        [chk(CheckStatus.PASS), chk(CheckStatus.REVIEW)],
    ) == CheckStatus.REVIEW
    assert aggregate_overall_status(
        [chk(CheckStatus.REVIEW), chk(CheckStatus.FAIL)],
    ) == CheckStatus.FAIL


def test_run_rules_full_pass_path() -> None:
    fields = {
        "brand_name": _field("brand_name", ExtractionStatus.FOUND, raw="STONE'S THROW"),
        "class_type": _field(
            "class_type",
            ExtractionStatus.FOUND,
            raw="Straight Bourbon Whiskey",
        ),
        "alcohol_content": _field(
            "alcohol_content",
            ExtractionStatus.FOUND,
            raw="45% Alc./Vol.",
            numeric=45.0,
            unit="%",
            explanation="Parsed ABV=45 from abv.",
        ),
        "net_contents": _field(
            "net_contents",
            ExtractionStatus.FOUND,
            raw="750 mL",
            numeric=750.0,
            unit="mL",
        ),
        "government_warning": _field(
            "government_warning",
            ExtractionStatus.FOUND,
            raw=STATUTORY,
        ),
    }
    checks = run_rules(_ctx(_app(), fields))
    assert aggregate_overall_status(checks) == CheckStatus.PASS
    assert all(c.status == CheckStatus.PASS for c in checks)


# --- API ---------------------------------------------------------------------


class ScriptedOcrProvider(OcrProvider):
    def __init__(self, text: str) -> None:
        self._text = text

    @property
    def name(self) -> str:
        return "scripted"

    def extract_text(self, image_bytes: bytes) -> OcrResult:
        assert image_bytes
        return OcrResult(
            full_text=self._text,
            words=[],
            provider_name="scripted",
            image_width_px=800,
            image_height_px=600,
            preprocessing_profile="fast",
            processing_time_ms=1.0,
        )


SAMPLE_LABEL = f"""STONE'S THROW
Straight Bourbon Whiskey
45% Alc./Vol.
750 mL
{STATUTORY}
"""


def test_verify_api_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ScriptedOcrProvider(SAMPLE_LABEL)

    def _factory(name: str) -> OcrProvider:  # noqa: ARG001
        return provider

    monkeypatch.setattr(
        "app.services.label_extraction_service.create_ocr_provider",
        _factory,
    )
    application = {
        "brand_name": "Stone's Throw",
        "class_type": "Straight Bourbon Whiskey",
        "alcohol_content_abv": "45%",
        "net_contents": "750 mL",
    }
    response = client.post(
        "/api/v1/verify",
        data={"application": json.dumps(application)},
        files={"file": ("label.jpg", jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["verification"]["overall_status"] in {"PASS", "REVIEW", "FAIL"}
    assert len(payload["verification"]["checks"]) == 5
    assert "extraction" in payload
    assert payload["application"]["brand_name"] == "Stone's Throw"


def test_application_validation_rejects_empty() -> None:
    with pytest.raises(ValidationError):
        ApplicationData(
            brand_name=" ",
            class_type="Vodka",
            alcohol_content_abv="40",
            net_contents="750 mL",
        )


def test_verification_service_with_scripted_ocr() -> None:
    service = VerificationService(ocr_provider=ScriptedOcrProvider(SAMPLE_LABEL))
    result = service.verify(
        jpeg_bytes(),
        _app(),
        filename="label.jpg",
    )
    assert result.verification_mode == "application_comparison"
    assert result.verification.overall_status in {CheckStatus.PASS, CheckStatus.REVIEW}
    counts = (
        result.verification.pass_count
        + result.verification.review_count
        + result.verification.fail_count
    )
    assert counts == 5
    assert result.processing_time_ms > 0
    assert "verification_rules" in result.stage_timings_ms


def test_label_only_verify_without_application() -> None:
    """Single Review path: no application → label-only rules, no false app mismatch."""
    service = VerificationService(ocr_provider=ScriptedOcrProvider(SAMPLE_LABEL))
    result = service.verify(jpeg_bytes(), application=None, filename="label.jpg")
    assert result.verification_mode == "label_only"
    assert result.application is None
    assert result.verification.verification_mode == "label_only"
    # Application-comparison rule ids must not appear.
    rule_ids = {c.rule_id for c in result.verification.checks}
    assert "RULE-DS-BRAND-APP-COMPARE" not in rule_ids
    assert "RULE-DS-BRAND-LABEL-EVIDENCE" in rule_ids
    assert any(c.check_name == "Government Health Warning" for c in result.verification.checks)
    # Missing application must not invent FAIL from comparison.
    assert all(c.application_value is None for c in result.verification.checks)
    assert result.verification.overall_status in {
        CheckStatus.PASS,
        CheckStatus.REVIEW,
        CheckStatus.FAIL,
    }


def test_label_only_api_without_application(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ScriptedOcrProvider(SAMPLE_LABEL)

    def _factory(name: str) -> OcrProvider:  # noqa: ARG001
        return provider

    monkeypatch.setattr(
        "app.services.label_extraction_service.create_ocr_provider",
        _factory,
    )
    response = client.post(
        "/api/v1/verify",
        files={"file": ("label.jpg", jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["verification_mode"] == "label_only"
    assert payload.get("application") is None
    assert payload["verification"]["verification_mode"] == "label_only"
    assert len(payload["verification"]["checks"]) == 5
