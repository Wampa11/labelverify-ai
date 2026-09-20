"""
Phase 8.9 selective brand OCR escalation tests.

Architectural responsibility: prove escalation triggers, reconcile outcomes,
and safe secondary-OCR disable/unavailable paths without fixture brand hard-codes.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.core.config import Settings
from app.extraction.brand_escalation import (
    collect_brand_escalation_triggers,
    reconcile_brand_evidence,
    run_brand_escalation,
    should_escalate_brand,
)
from app.models.extraction import ExtractedField, ExtractionMethod, ExtractionStatus
from app.ocr.base import OcrProvider, OcrResult, OcrWord
from app.services.label_extraction_service import LabelExtractionService


def _word(
    text: str,
    *,
    conf: float,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> OcrWord:
    return OcrWord(
        text=text,
        confidence=conf,
        bounding_box={"x_min": x0, "y_min": y0, "x_max": x1, "y_max": y1},
    )


def _ocr(text: str, words: list[OcrWord], *, w: int = 800, h: int = 600) -> OcrResult:
    return OcrResult(
        full_text=text,
        words=words,
        provider_name="tesseract",
        image_width_px=w,
        image_height_px=h,
        preprocessing_profile="fast",
    )


def _field(
    *,
    status: ExtractionStatus,
    raw: str | None,
    reason: str | None = None,
    integrity: list[str] | None = None,
) -> ExtractedField:
    hints: dict = {}
    if reason:
        hints["reason"] = reason
    if integrity:
        hints["integrity_issues"] = integrity
    return ExtractedField(
        field_name="brand_name",
        status=status,
        raw_text=raw,
        normalized_value=raw,
        extraction_method=ExtractionMethod.LAYOUT_HEURISTIC,
        explanation="test",
        ai_fallback_hints=hints,
    )


class _ScriptedOcr(OcrProvider):
    """Returns canned OCR results in call order."""

    def __init__(self, name: str, results: list[OcrResult]) -> None:
        self._name = name
        self._results = list(results)
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return True

    def extract_text(self, image_bytes: bytes) -> OcrResult:
        self.calls += 1
        if not self._results:
            return OcrResult(full_text="", words=[], provider_name=self._name)
        return self._results.pop(0)


def test_a_clean_brand_no_escalation_triggers() -> None:
    ocr = _ocr(
        "RIVER BEND\nDISTILLERY",
        [
            _word("RIVER", conf=0.95, x0=40, y0=30, x1=180, y1=90),
            _word("BEND", conf=0.95, x0=190, y0=30, x1=320, y1=90),
        ],
    )
    brand = _field(status=ExtractionStatus.FOUND, raw="RIVER BEND")
    assert should_escalate_brand(brand, ocr) is False
    assert collect_brand_escalation_triggers(brand, ocr) == []


def test_b_uncertain_brand_triggers_region_retry() -> None:
    ocr = _ocr("hispering =\nBourbon", [_word("hispering", conf=0.4, x0=10, y0=20, x1=200, y1=80)])
    brand = _field(
        status=ExtractionStatus.UNCERTAIN,
        raw="hispering =",
        reason="brand_integrity",
        integrity=["ocr_artifact_symbol", "leading_lowercase"],
    )
    triggers = collect_brand_escalation_triggers(brand, ocr)
    assert any(t.startswith("brand_uncertain") for t in triggers)
    assert should_escalate_brand(brand, ocr) is True


def test_c_aple_like_suspicious_found_region_supersedes() -> None:
    # Tall glyphs starting well inset → soft FOUND suspicion (no brand dictionary).
    whole = _ocr(
        "APLE CREEK",
        [
            _word("APLE", conf=0.93, x0=120, y0=80, x1=280, y1=180),
            _word("CREEK", conf=0.90, x0=300, y0=80, x1=480, y1=180),
        ],
        w=500,
        h=600,
    )
    brand = _field(status=ExtractionStatus.FOUND, raw="APLE CREEK")
    assert "prominent_left_inset" in collect_brand_escalation_triggers(brand, whole)

    region_ocr = _ocr(
        "MAPLE CREEK\nDISTILLERY",
        [
            _word("MAPLE", conf=0.95, x0=10, y0=5, x1=120, y1=60),
            _word("CREEK", conf=0.95, x0=130, y0=5, x1=250, y1=60),
        ],
        w=260,
        h=80,
    )
    primary = _ScriptedOcr("tesseract", [region_ocr])
    result = run_brand_escalation(
        prepared_image_bytes=_tiny_png(),
        guide_ocr=whole,
        brand=brand,
        primary_ocr=primary,
        secondary_ocr=None,
        secondary_enabled=False,
    )
    assert result.triggered is True
    assert result.tesseract_region_ran is True
    assert primary.calls == 1
    assert result.final_brand is not None
    assert result.final_brand.status == ExtractionStatus.FOUND
    assert "MAPLE" in (result.final_brand.normalized_value or "").upper()
    assert any("superseded" in o or "replaced" in o for o in result.reconcile_outcomes)


def test_d_region_uncertain_marks_secondary_eligible() -> None:
    whole = _ocr(
        "ie DISTILLERY",
        [_word("ie", conf=0.2, x0=100, y0=40, x1=220, y1=160)],
        w=500,
        h=600,
    )
    brand = _field(
        status=ExtractionStatus.UNCERTAIN,
        raw="ie DISTILLERY",
        reason="brand_integrity",
        integrity=["leading_lowercase"],
    )
    region_ocr = _ocr("ie", [_word("ie", conf=0.3, x0=5, y0=5, x1=40, y1=40)], w=80, h=50)
    secondary_ocr = _ocr(
        "WHISPERING PINE",
        [
            _word("WHISPERING", conf=0.9, x0=5, y0=5, x1=140, y1=40),
            _word("PINE", conf=0.9, x0=150, y0=5, x1=220, y1=40),
        ],
        w=230,
        h=50,
    )
    primary = _ScriptedOcr("tesseract", [region_ocr])
    secondary = _ScriptedOcr("rapidocr", [secondary_ocr])
    result = run_brand_escalation(
        prepared_image_bytes=_tiny_png(),
        guide_ocr=whole,
        brand=brand,
        primary_ocr=primary,
        secondary_ocr=secondary,
        secondary_enabled=True,
    )
    assert result.secondary_ran is True
    assert result.final_brand is not None
    assert result.final_brand.status == ExtractionStatus.FOUND
    assert "WHISPERING" in (result.final_brand.normalized_value or "").upper()


def test_e_secondary_disabled_safe_uncertain() -> None:
    whole = _ocr("x", [_word("x", conf=0.2, x0=10, y0=10, x1=40, y1=40)])
    brand = _field(status=ExtractionStatus.UNCERTAIN, raw="x", reason="brand_integrity")
    region_ocr = _ocr("x", [_word("x", conf=0.2, x0=2, y0=2, x1=20, y1=20)], w=40, h=40)
    primary = _ScriptedOcr("tesseract", [region_ocr])
    secondary = _ScriptedOcr("rapidocr", [])
    result = run_brand_escalation(
        prepared_image_bytes=_tiny_png(),
        guide_ocr=whole,
        brand=brand,
        primary_ocr=primary,
        secondary_ocr=secondary,
        secondary_enabled=False,
    )
    assert result.secondary_ran is False
    assert result.secondary_skipped_reason == "secondary_ocr_disabled"
    assert secondary.calls == 0
    assert result.final_brand is not None
    assert result.final_brand.status == ExtractionStatus.UNCERTAIN


def test_f_secondary_unavailable_no_crash() -> None:
    whole = _ocr("x", [_word("x", conf=0.2, x0=10, y0=10, x1=40, y1=40)])
    brand = _field(status=ExtractionStatus.NOT_FOUND, raw=None)
    region_ocr = _ocr("", [], w=40, h=40)
    primary = _ScriptedOcr("tesseract", [region_ocr])
    result = run_brand_escalation(
        prepared_image_bytes=_tiny_png(),
        guide_ocr=whole,
        brand=brand,
        primary_ocr=primary,
        secondary_ocr=None,
        secondary_enabled=True,
    )
    assert result.secondary_ran is False
    assert result.secondary_skipped_reason == "secondary_provider_unavailable"


def test_g_tesseract_vs_rapidocr_conflict_uncertain() -> None:
    base = _field(status=ExtractionStatus.FOUND, raw="ALPHA RIDGE")
    challenger = _field(status=ExtractionStatus.FOUND, raw="BETA VALLEY")
    merged, outcome = reconcile_brand_evidence(
        base,
        challenger,
        challenger_source="rapidocr_brand_region",
        base_was_suspicious=False,
    )
    assert merged.status == ExtractionStatus.UNCERTAIN
    assert "conflict" in outcome
    assert merged.ai_fallback_hints.get("reason") == "brand_ocr_conflict"


def test_h_matching_evidence_reinforced() -> None:
    base = _field(status=ExtractionStatus.FOUND, raw="RIVER BEND")
    challenger = _field(status=ExtractionStatus.FOUND, raw="river bend")
    merged, outcome = reconcile_brand_evidence(
        base,
        challenger,
        challenger_source="tesseract_brand_region",
        base_was_suspicious=True,
    )
    assert merged.status == ExtractionStatus.FOUND
    assert "reinforced" in outcome
    assert merged.extraction_method == ExtractionMethod.COMBINED


def test_i_clean_label_skips_region_ocr() -> None:
    """When brand FOUND without suspicion, region OCR is not invoked."""
    primary = MagicMock(spec=OcrProvider)
    primary.name = "tesseract"
    primary.is_available.return_value = True

    clean = _ocr(
        "RIVER BEND\n45% Alc./Vol.\n750 mL",
        [
            _word("RIVER", conf=0.95, x0=30, y0=20, x1=140, y1=70),
            _word("BEND", conf=0.95, x0=150, y0=20, x1=250, y1=70),
        ],
    )
    brand = _field(status=ExtractionStatus.FOUND, raw="RIVER BEND")
    result = run_brand_escalation(
        prepared_image_bytes=_tiny_png(),
        guide_ocr=clean,
        brand=brand,
        primary_ocr=primary,
        secondary_ocr=None,
        secondary_enabled=False,
    )
    assert result.triggered is False
    assert primary.extract_text.call_count == 0


def test_j_evidence_method_suffix_preserved() -> None:
    whole = _ocr(
        "APLE CREEK",
        [
            _word("APLE", conf=0.93, x0=120, y0=80, x1=280, y1=180),
            _word("CREEK", conf=0.90, x0=300, y0=80, x1=480, y1=180),
        ],
        w=500,
        h=600,
    )
    brand = _field(status=ExtractionStatus.FOUND, raw="APLE CREEK")
    region_ocr = _ocr(
        "MAPLE CREEK",
        [
            _word("MAPLE", conf=0.95, x0=10, y0=5, x1=120, y1=60),
            _word("CREEK", conf=0.95, x0=130, y0=5, x1=250, y1=60),
        ],
        w=260,
        h=80,
    )
    result = run_brand_escalation(
        prepared_image_bytes=_tiny_png(),
        guide_ocr=whole,
        brand=brand,
        primary_ocr=_ScriptedOcr("tesseract", [region_ocr]),
        secondary_ocr=None,
        secondary_enabled=False,
    )
    assert result.evidence_method_suffix == "brand_region"
    assert result.as_dict()["evidence_method_suffix"] == "brand_region"


def test_secondary_provider_resolve_safe() -> None:
    settings = Settings(
        brand_region_ocr_enabled=True,
        secondary_ocr_enabled=True,
        secondary_ocr_provider="rapidocr",
        openai_enabled=False,
    )
    service = LabelExtractionService(
        settings=settings,
        ocr_provider=_ScriptedOcr("tesseract", []),
    )
    resolved = service._resolve_secondary_provider()
    assert resolved is None or resolved.is_available()


def _tiny_png() -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (400, 500), color=(245, 240, 230)).save(buf, format="PNG")
    return buf.getvalue()
