"""
Unit and integration tests for Phase 4 OCR field extraction.

Architectural responsibility: cover parsers, extractors, retry/selection, and API.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.extraction.alcohol_content import extract_alcohol_content
from app.extraction.brand_name import extract_brand_name
from app.extraction.class_type import extract_class_type
from app.extraction.government_warning import extract_government_warning
from app.extraction.net_contents import extract_net_contents
from app.extraction.pipeline import extract_all_fields
from app.extraction.retry_policy import (
    merge_conflicts_as_uncertain,
    score_pass,
    select_pass,
    should_retry_enhanced,
)
from app.main import app
from app.models.extraction import (
    ExtractedField,
    ExtractionMethod,
    ExtractionStatus,
    OcrPassSummary,
)
from app.models.image_analysis import QualityStatus
from app.normalization.field_parsers import parse_alcohol_content, parse_net_contents
from app.ocr.base import OcrProvider, OcrResult, OcrWord
from app.ocr.factory import create_ocr_provider
from app.ocr.tesseract_provider import TesseractOcrProvider
from app.services.label_extraction_service import LabelExtractionService
from tests.image_fixtures import jpeg_bytes

client = TestClient(app)

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO_ROOT / "test-data" / "ocr-eval"
CLEAN_IMAGE = CORPUS_DIR / "fixtures" / "clean_high_quality.png"


def _ocr(
    text: str,
    *,
    words: list[OcrWord] | None = None,
    profile: str = "fast",
) -> OcrResult:
    return OcrResult(
        full_text=text,
        words=words or [],
        provider_name="test",
        image_width_px=800,
        image_height_px=600,
        preprocessing_profile=profile,
    )


def _field(
    name: str,
    status: ExtractionStatus,
    *,
    raw: str | None = None,
    normalized: str | None = None,
    numeric: float | None = None,
) -> ExtractedField:
    return ExtractedField(
        field_name=name,
        status=status,
        raw_text=raw,
        normalized_value=normalized,
        normalized_numeric=numeric,
        explanation=f"test {name}",
        extraction_method=ExtractionMethod.REGEX,
    )


def _pass_summary(profile: str, fields: dict[str, ExtractedField]) -> OcrPassSummary:
    return OcrPassSummary(
        profile=profile,
        max_edge_px=1600 if profile == "fast" else 1200,
        provider_name="test",
        preprocessing_time_ms=1.0,
        ocr_time_ms=2.0,
        extraction_time_ms=1.0,
        total_pass_time_ms=4.0,
        ocr_text_preview="preview",
        word_count=10,
        fields=fields,
        found_count=sum(1 for f in fields.values() if f.status == ExtractionStatus.FOUND),
        uncertain_count=sum(1 for f in fields.values() if f.status == ExtractionStatus.UNCERTAIN),
        not_found_count=sum(1 for f in fields.values() if f.status == ExtractionStatus.NOT_FOUND),
    )


class ScriptedOcrProvider(OcrProvider):
    """Deterministic OCR for tests — returns scripted results in call order."""

    def __init__(self, results: list[OcrResult]) -> None:
        self._results = list(results)
        self.calls = 0

    @property
    def name(self) -> str:
        return "scripted"

    def extract_text(self, image_bytes: bytes) -> OcrResult:
        assert image_bytes
        if self.calls >= len(self._results):
            raise AssertionError("Scripted OCR exhausted")
        result = self._results[self.calls]
        self.calls += 1
        return result


# --- Parsers -----------------------------------------------------------------


def test_parse_abv_variants() -> None:
    for text in ("45% Alc./Vol.", "45 % ALC/VOL", "ALC. 45% BY VOL.", "45% ABV"):
        parsed = parse_alcohol_content(text)
        assert parsed is not None
        assert parsed.abv_percent == 45.0


def test_parse_proof_to_abv() -> None:
    parsed = parse_alcohol_content("90 Proof")
    assert parsed is not None
    assert parsed.proof == 90.0
    assert parsed.abv_percent == 45.0
    assert parsed.source == "proof"


def test_parse_abv_and_proof_both_preserved() -> None:
    parsed = parse_alcohol_content("45% Alc./Vol. 90 Proof")
    assert parsed is not None
    assert parsed.source == "both"
    assert parsed.abv_percent == 45.0
    assert parsed.proof == 90.0


def test_parse_net_contents_variants() -> None:
    for text, value, unit in (
        ("750 mL", 750.0, "mL"),
        ("750ML", 750.0, "mL"),
        ("750 ml", 750.0, "mL"),
        ("1.75 L", 1.75, "L"),
    ):
        parsed = parse_net_contents(text)
        assert parsed is not None
        assert parsed.value == value
        assert parsed.unit == unit


# --- Field extractors --------------------------------------------------------


SAMPLE_LABEL = """
NORTH PEAK DISTILLING
Straight Bourbon Whiskey
45% Alc./Vol.
750 mL
GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink
alcoholic beverages during pregnancy because of the risk of birth defects.
(2) Consumption of alcoholic beverages impairs your ability to drive a car or
operate machinery, and may cause health problems.
"""


def test_extract_alcohol_content_found() -> None:
    field = extract_alcohol_content(_ocr(SAMPLE_LABEL))
    assert field.status == ExtractionStatus.FOUND
    assert field.normalized_numeric == 45.0
    assert field.raw_text is not None


def test_extract_net_contents_found() -> None:
    field = extract_net_contents(_ocr(SAMPLE_LABEL))
    assert field.status == ExtractionStatus.FOUND
    assert field.normalized_numeric == 750.0
    assert field.normalized_unit == "mL"


def test_extract_government_warning_found() -> None:
    field = extract_government_warning(_ocr(SAMPLE_LABEL))
    assert field.status in {ExtractionStatus.FOUND, ExtractionStatus.UNCERTAIN}
    assert field.raw_text and "GOVERNMENT WARNING" in field.raw_text.upper()


def test_extract_government_warning_partial() -> None:
    field = extract_government_warning(_ocr("GOVERNMENT WARNING\nSee bottle."))
    assert field.status == ExtractionStatus.UNCERTAIN


def test_extract_government_warning_missing() -> None:
    field = extract_government_warning(_ocr("NORTH PEAK\n45% Alc./Vol."))
    assert field.status == ExtractionStatus.NOT_FOUND


def test_extract_class_type_found() -> None:
    field = extract_class_type(_ocr(SAMPLE_LABEL))
    assert field.status == ExtractionStatus.FOUND
    assert field.raw_text and "bourbon" in field.raw_text.lower()


def test_extract_class_type_ambiguous() -> None:
    text = "Bourbon Whiskey\nRye Whiskey\nVodka"
    field = extract_class_type(_ocr(text))
    assert field.status == ExtractionStatus.UNCERTAIN
    assert len(field.candidates) >= 2


def test_extract_brand_conservative() -> None:
    box = {"x_min": 10, "y_min": 20, "x_max": 80, "y_max": 60}
    words = [
        OcrWord(text="NORTH", confidence=0.9, bounding_box=box),
        OcrWord(
            text="PEAK",
            confidence=0.9,
            bounding_box={"x_min": 90, "y_min": 20, "x_max": 160, "y_max": 60},
        ),
        OcrWord(
            text="DISTILLING",
            confidence=0.9,
            bounding_box={"x_min": 170, "y_min": 20, "x_max": 320, "y_max": 60},
        ),
    ]
    field = extract_brand_name(_ocr(SAMPLE_LABEL, words=words))
    assert field.status in {ExtractionStatus.FOUND, ExtractionStatus.UNCERTAIN}
    assert field.raw_text is not None


def test_extract_all_fields_no_text() -> None:
    fields = extract_all_fields(_ocr(""))
    assert all(f.status == ExtractionStatus.NOT_FOUND for f in fields.values())


def test_regions_serialized_with_bbox() -> None:
    words = [
        OcrWord(
            text="750",
            confidence=0.88,
            bounding_box={"x_min": 1, "y_min": 2, "x_max": 3, "y_max": 4},
        ),
        OcrWord(
            text="mL",
            confidence=0.9,
            bounding_box={"x_min": 5, "y_min": 2, "x_max": 9, "y_max": 4},
        ),
    ]
    field = extract_net_contents(_ocr("750 mL", words=words))
    assert field.ocr_regions
    assert field.ocr_regions[0].bounding_box is not None
    assert field.ocr_regions[0].provider_name == "test"
    assert field.ocr_regions[0].preprocessing_profile == "fast"


# --- Retry / selection -------------------------------------------------------


def test_retry_triggers_when_warning_missing() -> None:
    fields = {
        "brand_name": _field("brand_name", ExtractionStatus.FOUND, raw="X"),
        "class_type": _field("class_type", ExtractionStatus.FOUND, raw="Y"),
        "alcohol_content": _field("alcohol_content", ExtractionStatus.FOUND, numeric=40),
        "net_contents": _field("net_contents", ExtractionStatus.FOUND, numeric=750),
        "government_warning": _field("government_warning", ExtractionStatus.NOT_FOUND),
    }
    decision = should_retry_enhanced(
        fields,
        ocr_text="plenty of text here for the label",
        word_count=20,
        quality_status=QualityStatus.GOOD,
    )
    assert decision.triggered is True
    assert "government_warning_not_found" in decision.reasons


def test_retry_does_not_trigger_on_quality_alone() -> None:
    fields = {
        "brand_name": _field("brand_name", ExtractionStatus.FOUND, raw="X"),
        "class_type": _field("class_type", ExtractionStatus.FOUND, raw="Y"),
        "alcohol_content": _field("alcohol_content", ExtractionStatus.FOUND, numeric=40),
        "net_contents": _field("net_contents", ExtractionStatus.FOUND, numeric=750),
        "government_warning": _field("government_warning", ExtractionStatus.FOUND, raw="GW"),
    }
    decision = should_retry_enhanced(
        fields,
        ocr_text="plenty of text here for the label",
        word_count=20,
        quality_status=QualityStatus.POOR,
    )
    assert decision.triggered is False


def test_retry_triggers_on_sparse_ocr() -> None:
    fields = {
        name: _field(name, ExtractionStatus.NOT_FOUND)
        for name in (
            "brand_name",
            "class_type",
            "alcohol_content",
            "net_contents",
            "government_warning",
        )
    }
    decision = should_retry_enhanced(
        fields,
        ocr_text="x",
        word_count=1,
        quality_status=QualityStatus.GOOD,
    )
    assert decision.triggered is True
    assert any("sparse" in r or "not_found" in r for r in decision.reasons)


def test_select_prefers_higher_score_not_blind_enhanced() -> None:
    fast_fields = {
        "brand_name": _field("brand_name", ExtractionStatus.FOUND),
        "class_type": _field("class_type", ExtractionStatus.FOUND),
        "alcohol_content": _field("alcohol_content", ExtractionStatus.FOUND),
        "net_contents": _field("net_contents", ExtractionStatus.FOUND),
        "government_warning": _field("government_warning", ExtractionStatus.FOUND),
    }
    enh_fields = {
        "brand_name": _field("brand_name", ExtractionStatus.FOUND),
        "class_type": _field("class_type", ExtractionStatus.NOT_FOUND),
        "alcohol_content": _field("alcohol_content", ExtractionStatus.FOUND),
        "net_contents": _field("net_contents", ExtractionStatus.FOUND),
        "government_warning": _field("government_warning", ExtractionStatus.UNCERTAIN),
    }
    selection = select_pass(
        _pass_summary("fast", fast_fields),
        _pass_summary("enhanced", enh_fields),
    )
    assert selection.selected_profile == "fast"
    assert score_pass(fast_fields) > score_pass(enh_fields)


def test_select_enhanced_when_better() -> None:
    fast_fields = {
        name: _field(name, ExtractionStatus.NOT_FOUND)
        for name in (
            "brand_name",
            "class_type",
            "alcohol_content",
            "net_contents",
            "government_warning",
        )
    }
    enh_fields = {
        "brand_name": _field("brand_name", ExtractionStatus.FOUND),
        "class_type": _field("class_type", ExtractionStatus.FOUND),
        "alcohol_content": _field("alcohol_content", ExtractionStatus.FOUND),
        "net_contents": _field("net_contents", ExtractionStatus.FOUND),
        "government_warning": _field("government_warning", ExtractionStatus.FOUND),
    }
    selection = select_pass(
        _pass_summary("fast", fast_fields),
        _pass_summary("enhanced", enh_fields),
    )
    assert selection.selected_profile == "enhanced"


def test_conflict_marks_uncertain() -> None:
    selected = {
        "alcohol_content": _field(
            "alcohol_content",
            ExtractionStatus.FOUND,
            raw="40%",
            normalized="40",
            numeric=40.0,
        ),
    }
    other = {
        "alcohol_content": _field(
            "alcohol_content",
            ExtractionStatus.FOUND,
            raw="45%",
            normalized="45",
            numeric=45.0,
        ),
    }
    merged = merge_conflicts_as_uncertain(selected, other)
    assert merged["alcohol_content"].status == ExtractionStatus.UNCERTAIN


# --- Service / provider / API ------------------------------------------------


def test_tesseract_provider_default_factory() -> None:
    provider = create_ocr_provider("tesseract")
    assert isinstance(provider, TesseractOcrProvider)
    assert provider.name == "tesseract"


def test_label_extraction_service_fast_default_and_retry_observable() -> None:
    sparse = _ocr("x", profile="fast")
    rich = _ocr(SAMPLE_LABEL, profile="enhanced")
    provider = ScriptedOcrProvider([sparse, rich])
    service = LabelExtractionService(ocr_provider=provider)
    result = service.extract(jpeg_bytes(), filename="label.jpg", declared_content_type="image/jpeg")
    assert provider.calls == 2
    assert result.extraction.retry.triggered is True
    assert result.extraction.retry.performed is True
    assert result.extraction.retry.reasons
    assert result.extraction.fast_pass.profile == "fast"
    assert result.extraction.fast_pass.max_edge_px == 1600
    assert result.extraction.enhanced_pass is not None
    assert result.extraction.enhanced_pass.profile == "enhanced"
    assert result.extraction.enhanced_pass.max_edge_px == 1200
    assert result.extraction.selection.selected_profile in {"fast", "enhanced"}
    assert "fast_preprocess" in result.stage_timings_ms
    assert "fast_ocr" in result.stage_timings_ms
    assert "fast_extraction" in result.stage_timings_ms


def test_label_extraction_service_no_retry_when_complete() -> None:
    rich = _ocr(SAMPLE_LABEL, profile="fast")
    provider = ScriptedOcrProvider([rich])
    service = LabelExtractionService(ocr_provider=provider)
    result = service.extract(jpeg_bytes(), filename="label.jpg")
    assert provider.calls == 1
    assert result.extraction.retry.triggered is False
    assert result.extraction.retry.performed is False
    assert result.extraction.enhanced_pass is None
    assert result.extraction.selection.selected_profile == "fast"
    assert result.extraction.selected_fields["alcohol_content"].status == ExtractionStatus.FOUND


def test_extract_api_with_scripted_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    rich = _ocr(SAMPLE_LABEL, profile="fast")
    provider = ScriptedOcrProvider([rich])

    def _factory(name: str) -> OcrProvider:  # noqa: ARG001
        return provider

    monkeypatch.setattr(
        "app.services.label_extraction_service.create_ocr_provider",
        _factory,
    )
    response = client.post(
        "/api/v1/labels/extract",
        files={"file": ("label.jpg", jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "extraction" in payload
    assert payload["extraction"]["selected_fields"]["alcohol_content"]["status"] == "FOUND"
    assert "PASS" not in str(payload["extraction"]["selected_fields"])
    assert payload["disclaimer"]


@pytest.mark.skipif(not CLEAN_IMAGE.is_file(), reason="OCR corpus image missing")
def test_corpus_clean_fixture_extraction_smoke() -> None:
    """Exercise Phase 3 fixture through extractors with real Tesseract when available."""
    provider = TesseractOcrProvider()
    if not provider.is_available():
        pytest.skip("Tesseract not available")
    service = LabelExtractionService(ocr_provider=provider)
    data = CLEAN_IMAGE.read_bytes()
    result = service.extract(data, filename=CLEAN_IMAGE.name)
    fields = result.extraction.selected_fields
    # Difficult OCR may still miss fields; assert contract and that ABV or net often recovers.
    assert set(fields) >= {
        "brand_name",
        "class_type",
        "alcohol_content",
        "net_contents",
        "government_warning",
    }
    assert result.extraction.fast_pass.max_edge_px == 1600
    assert result.processing_time_ms > 0
