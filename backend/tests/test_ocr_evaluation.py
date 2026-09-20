"""
Unit tests for OCR contracts, metrics, ground truth, and evaluation reporting.

Architectural responsibility: keep OCR evaluation logic testable without engines
when possible; probe providers for failure behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ocr.base import OcrResult, OcrWord
from app.ocr.errors import OcrProviderError
from app.ocr.evaluate.corpus import generate_corpus
from app.ocr.evaluate.ground_truth import FixtureGroundTruth, load_corpus_manifest
from app.ocr.evaluate.metrics import (
    character_error_rate,
    field_recovered,
    normalize_for_compare,
    score_compliance_fields,
)
from app.ocr.evaluate.report import write_json_report, write_markdown_summary
from app.ocr.evaluate.runner import EvaluationReport, RunRecord
from app.ocr.factory import create_ocr_provider
from app.ocr.stub import StubOcrProvider
from app.preprocessing.ocr_prepare import OcrPreprocessProfile, prepare_for_ocr_from_bytes
from tests.image_fixtures import jpeg_bytes


def test_stub_provider_fails_observably() -> None:
    provider = StubOcrProvider()
    assert provider.is_available() is False
    with pytest.raises(OcrProviderError) as exc:
        provider.extract_text(jpeg_bytes())
    assert exc.value.code == "ocr_not_configured"


def test_empty_image_rejected_by_tesseract_provider_without_binary() -> None:
    provider = create_ocr_provider("tesseract")
    with pytest.raises(OcrProviderError) as exc:
        provider.extract_text(b"")
    assert exc.value.code == "empty_image"


def test_ocr_result_bounding_box_serialization() -> None:
    result = OcrResult(
        full_text="Bourbon",
        words=[
            OcrWord(
                text="Bourbon",
                confidence=0.9,
                bounding_box={"x_min": 1, "y_min": 2, "x_max": 10, "y_max": 20},
            ),
        ],
        provider_name="unit",
        image_width_px=100,
        image_height_px=200,
    )
    payload = result.model_dump()
    assert payload["words"][0]["bounding_box"]["x_min"] == 1
    assert result.has_bounding_boxes is True
    assert result.has_text is True


def test_confidence_none_when_not_provided() -> None:
    word = OcrWord(text="Whiskey", confidence=None)
    assert word.confidence is None


def test_character_error_rate_and_field_recovery() -> None:
    assert character_error_rate("abc", "abc") == 0.0
    assert character_error_rate("abc", "axc") == pytest.approx(1 / 3)
    assert normalize_for_compare("45% Alc./Vol.") == "45% alc./vol."

    from app.ocr.evaluate.ground_truth import ComplianceFieldTruth

    truth = ComplianceFieldTruth(exact_text="45% Alc./Vol.", semantic_value="45")
    assert field_recovered("Alcohol 45 percent by volume", truth) is True
    assert field_recovered("no numbers here", truth) is False


def test_prepare_fast_vs_enhanced(tmp_path: Path) -> None:
    data = jpeg_bytes(width=800, height=600)
    fast = prepare_for_ocr_from_bytes(
        data,
        profile=OcrPreprocessProfile.FAST,
        max_edge_px=1200,
    )
    enhanced = prepare_for_ocr_from_bytes(
        data,
        profile=OcrPreprocessProfile.ENHANCED,
        max_edge_px=1200,
    )
    assert fast.profile == OcrPreprocessProfile.FAST
    assert enhanced.profile == OcrPreprocessProfile.ENHANCED
    assert any(op.name == "mild_denoise" and op.applied for op in enhanced.operations)
    assert any(op.name == "enhanced_skipped" for op in fast.operations)


def test_generate_and_load_corpus(tmp_path: Path) -> None:
    root = generate_corpus(tmp_path / "ocr-eval")
    fixtures = load_corpus_manifest(root)
    assert len(fixtures) >= 11
    assert all(isinstance(item, FixtureGroundTruth) for item in fixtures)
    assert (root / "fixtures" / fixtures[0].image_file).is_file()


def test_score_compliance_fields_and_report(tmp_path: Path) -> None:
    root = generate_corpus(tmp_path / "ocr-eval")
    fixture = load_corpus_manifest(root)[0]
    text = (
        f"{fixture.brand_name.exact_text}\n{fixture.class_type.exact_text}\n"
        f"{fixture.alcohol_content_abv.exact_text}\n{fixture.net_contents.exact_text}\n"
        f"{fixture.government_health_warning.exact_text}"
    )
    scores = score_compliance_fields(text, fixture)
    assert all(scores.values())

    report = EvaluationReport(
        generated_at="2026-09-19T00:00:00Z",
        environment={"python": "3.12"},
        providers_requested=["tesseract"],
        providers_available=["tesseract"],
        providers_unavailable={},
        preprocess_profiles=["fast"],
        max_edge_sizes=[1200],
        records=[
            RunRecord(
                fixture_id=fixture.fixture_id,
                category=fixture.category,
                provider="tesseract",
                preprocess_profile="fast",
                max_edge_px=1200,
                success=True,
                failure_kind=None,
                failure_message=None,
                preprocessing_time_ms=10,
                ocr_time_ms=20,
                total_pipeline_time_ms=30,
                character_error_rate=0.1,
                field_recovery=scores,
                fields_recovered_count=5,
                fields_total=5,
                has_bounding_boxes=True,
                word_count=10,
                ocr_text_preview=text[:100],
            ),
        ],
    )
    json_path = tmp_path / "out.json"
    md_path = tmp_path / "out.md"
    write_json_report(report, json_path)
    summary = write_markdown_summary(report, md_path)
    assert json.loads(json_path.read_text(encoding="utf-8"))["records"]
    assert "OCR Evaluation Summary" in summary
