"""
Tests for image validation, preprocessing, quality, and analyze API.

Architectural responsibility: cover Phase 2 upload safety and preprocessing behavior.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.core.exceptions import ImageValidationError
from app.main import app
from app.models.image_analysis import QualityStatus
from app.preprocessing.formats import DetectedContentKind, sniff_content_kind
from app.preprocessing.orientation import apply_exif_orientation
from app.preprocessing.pipeline import ImagePreprocessPipeline
from app.preprocessing.quality import assess_image_quality
from app.preprocessing.transforms import to_grayscale_array
from app.preprocessing.validation import validate_image_bytes
from app.services.image_analysis_service import ImageAnalysisService
from tests.image_fixtures import (
    blurred_jpeg_bytes,
    corrupt_jpeg_bytes,
    dark_jpeg_bytes,
    jpeg_bytes,
    jpeg_with_exif_orientation,
    low_contrast_jpeg_bytes,
    overexposed_jpeg_bytes,
    png_bytes,
    tiny_jpeg_bytes,
    webp_bytes,
)

client = TestClient(app)


def test_sniff_jpeg_png_webp() -> None:
    assert sniff_content_kind(jpeg_bytes()) == DetectedContentKind.JPEG
    assert sniff_content_kind(png_bytes()) == DetectedContentKind.PNG
    assert sniff_content_kind(webp_bytes()) == DetectedContentKind.WEBP


def test_validate_accepts_jpeg_png_webp() -> None:
    for payload in (jpeg_bytes(), png_bytes(), webp_bytes()):
        validation, image, fmt = validate_image_bytes(payload)
        assert validation.accepted is True
        assert fmt.value in {"jpeg", "png", "webp"}
        image.close()


def test_validate_rejects_empty() -> None:
    with pytest.raises(ImageValidationError) as exc:
        validate_image_bytes(b"")
    assert exc.value.code == "empty_file"


def test_validate_rejects_corrupt() -> None:
    with pytest.raises(ImageValidationError) as exc:
        validate_image_bytes(corrupt_jpeg_bytes())
    assert exc.value.code == "corrupt_image"


def test_validate_rejects_unsupported() -> None:
    with pytest.raises(ImageValidationError) as exc:
        validate_image_bytes(b"%PDF-1.4 fake")
    assert exc.value.code == "pdf_not_supported"


def test_validate_rejects_oversized() -> None:
    settings = Settings(max_upload_bytes=1000)
    payload = jpeg_bytes()
    assert len(payload) > 1000
    with pytest.raises(ImageValidationError) as exc:
        validate_image_bytes(payload, settings=settings)
    assert exc.value.code == "file_too_large"


def test_validate_rejects_tiny_dimensions() -> None:
    with pytest.raises(ImageValidationError) as exc:
        validate_image_bytes(tiny_jpeg_bytes())
    assert exc.value.code == "dimensions_too_small"


def test_exif_orientation_changes_layout() -> None:
    data = jpeg_with_exif_orientation(6)
    image = Image.open(io.BytesIO(data))
    oriented, changed = apply_exif_orientation(image)
    assert changed is True
    # Orientation 6 rotates 90° CW → width/height swap for 400x200 source.
    assert oriented.size == (200, 400)
    image.close()
    oriented.close()


def test_quality_blur_and_dark_and_contrast() -> None:
    blur = Image.open(io.BytesIO(blurred_jpeg_bytes())).convert("RGB")
    blur_q = assess_image_quality(to_grayscale_array(blur), width_px=640, height_px=480)
    assert blur_q.status in {QualityStatus.WARNING, QualityStatus.POOR}
    assert any("blur" in w.lower() for w in blur_q.warnings)

    dark = Image.open(io.BytesIO(dark_jpeg_bytes())).convert("RGB")
    dark_q = assess_image_quality(to_grayscale_array(dark), width_px=640, height_px=480)
    assert dark_q.status in {QualityStatus.WARNING, QualityStatus.POOR}

    low = Image.open(io.BytesIO(low_contrast_jpeg_bytes())).convert("RGB")
    low_q = assess_image_quality(to_grayscale_array(low), width_px=640, height_px=480)
    assert low_q.status in {QualityStatus.WARNING, QualityStatus.POOR}

    bright = Image.open(io.BytesIO(overexposed_jpeg_bytes())).convert("RGB")
    bright_q = assess_image_quality(to_grayscale_array(bright), width_px=640, height_px=480)
    assert bright_q.status in {QualityStatus.WARNING, QualityStatus.POOR}


def test_pipeline_returns_dual_representations() -> None:
    validation, image, _fmt = validate_image_bytes(jpeg_bytes())
    artifacts = ImagePreprocessPipeline().run(image)
    image.close()
    assert validation.accepted
    assert artifacts.display_base64
    assert artifacts.ocr_base64
    assert artifacts.display_media_type == "image/jpeg"
    assert artifacts.ocr_media_type == "image/png"
    assert artifacts.quality.status in {
        QualityStatus.GOOD,
        QualityStatus.WARNING,
        QualityStatus.POOR,
    }
    assert artifacts.preprocessing.operations


def test_service_analyze_includes_timing() -> None:
    result = ImageAnalysisService().analyze(jpeg_bytes(), filename="sample.jpg")
    assert result.processing_time_ms >= 0
    assert "validation" in result.stage_timings_ms
    assert "preprocessing" in result.stage_timings_ms
    assert result.analysis_id
    assert "data/" not in result.display_image_base64
    assert not result.display_image_base64.lower().startswith("file:")


def test_api_analyze_success_jpeg() -> None:
    response = client.post(
        "/api/v1/images/analyze",
        files={"file": ("label.jpg", jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["validation"]["accepted"] is True
    assert payload["metadata"]["format"] == "jpeg"
    assert payload["quality"]["status"] in {"GOOD", "WARNING", "POOR"}
    assert payload["processing_time_ms"] >= 0
    assert "display_image_base64" in payload
    assert "ocr_image_base64" in payload


def test_api_analyze_success_png_webp() -> None:
    for name, data, mime in (
        ("label.png", png_bytes(), "image/png"),
        ("label.webp", webp_bytes(), "image/webp"),
    ):
        response = client.post(
            "/api/v1/images/analyze",
            files={"file": (name, data, mime)},
        )
        assert response.status_code == 200, response.text


def test_api_analyze_rejects_empty() -> None:
    response = client.post(
        "/api/v1/images/analyze",
        files={"file": ("empty.jpg", b"", "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "empty_file"


def test_api_analyze_rejects_corrupt() -> None:
    response = client.post(
        "/api/v1/images/analyze",
        files={"file": ("bad.jpg", corrupt_jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "corrupt_image"


def test_api_analyze_rejects_unsupported_extension_disguised() -> None:
    response = client.post(
        "/api/v1/images/analyze",
        files={"file": ("notes.txt", b"hello world not an image", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unsupported_format"


def test_preprocess_budget_is_small_fraction_of_five_seconds() -> None:
    """
    Soft performance check: preprocessing should stay well under the 5s pipeline budget.

    Not a brittle exact-ms CI assertion — only fails if clearly pathological (>2s).
    """
    result = ImageAnalysisService().analyze(jpeg_bytes(width=1600, height=1200))
    assert result.processing_time_ms < 2000
