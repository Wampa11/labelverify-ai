"""
Brand diagnostics tests — scoring parity and safe report shape (no images required).
"""

from __future__ import annotations

from app.extraction.brand_diagnostics import diagnose_brand_from_ocr, score_candidates_detailed
from app.extraction.brand_name import _score_candidates, extract_brand_name
from app.ocr.base import OcrResult, OcrWord


def _ocr(text: str, words: list[OcrWord] | None = None) -> OcrResult:
    return OcrResult(
        full_text=text,
        words=words or [],
        provider_name="test",
        image_width_px=800,
        image_height_px=600,
        preprocessing_profile="fast",
    )


def test_score_candidates_detailed_matches_production_scores() -> None:
    text = "RIVER BEND\nDISTILLERY\n45% Alc./Vol.\n750 mL"
    words = [
        OcrWord(
            text="RIVER",
            confidence=0.9,
            bounding_box={"x_min": 40, "y_min": 20, "x_max": 140, "y_max": 70},
        ),
        OcrWord(
            text="BEND",
            confidence=0.9,
            bounding_box={"x_min": 150, "y_min": 20, "x_max": 240, "y_max": 70},
        ),
        OcrWord(
            text="DISTILLERY",
            confidence=0.9,
            bounding_box={"x_min": 60, "y_min": 90, "x_max": 220, "y_max": 120},
        ),
    ]
    ocr = _ocr(text, words)
    field = extract_brand_name(ocr)
    # Production filter is applied inside diagnose; compare scored lists on same filtered set.
    from app.extraction import brand_name as brand
    from app.extraction.ocr_support import lines_from_ocr
    from app.normalization.field_parsers import parse_alcohol_content, parse_net_contents

    lines = lines_from_ocr(ocr)
    filtered = [
        line
        for line in lines
        if not brand._SKIP_LINE.search(line)
        and parse_alcohol_content(line) is None
        and parse_net_contents(line) is None
        and not brand._looks_like_class(line)
        and not brand._looks_like_warning_fragment(line)
        and 3 <= len(line) <= 60
    ]
    production = _score_candidates(ocr, filtered)
    detailed = score_candidates_detailed(ocr, filtered)
    assert [(round(s, 6), line) for s, line in production] == [
        (round(item["score"], 6), item["line"]) for item in detailed
    ]
    assert field.normalized_value == "RIVER BEND"


def test_diagnose_brand_includes_ocr_and_selection_reason() -> None:
    ocr = _ocr("hispering =\nBourbon Whiskey\n40% Alc./Vol.")
    diag = diagnose_brand_from_ocr(ocr, source_pass="fast")
    assert diag["source_pass"] == "fast"
    assert "ocr_full_text" in diag
    assert "scored_candidates" in diag
    assert diag["extraction_status"] in {"FOUND", "UNCERTAIN", "NOT_FOUND"}
    assert "selection_reason" in diag
