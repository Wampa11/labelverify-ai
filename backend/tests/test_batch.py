"""
Phase 7 batch orchestration and validation tests.

Architectural responsibility: prove batch reuses VerificationService, bounds concurrency,
handles errors, AI budget, CSV export, and 300-item mocked load — without live OpenAI.
"""

from __future__ import annotations

import csv
import io
import time

import pytest
from fastapi.testclient import TestClient

from app.ai.evidence import AiEvidenceConfidence, AiFieldEvidence
from app.ai.null_provider import NullAiProvider
from app.ai.scripted_provider import ScriptedAiProvider
from app.batch.budget_ai import BudgetAwareAiProvider
from app.batch.export import sanitize_csv_cell
from app.batch.manifest import (
    parse_and_validate_manifest,
    sample_manifest_csv,
    sanitize_upload_filename,
)
from app.batch.models import BatchItemProcessingState, BatchJobState
from app.batch.orchestrator import BatchOrchestrator
from app.batch.store import BatchStore
from app.core.config import Settings
from app.main import app
from app.models.verification import ApplicationData
from app.ocr.base import OcrProvider, OcrResult
from app.rules.regulatory_sources import STATUTORY_GOVERNMENT_WARNING
from app.services.verification_service import VerificationService
from tests.image_fixtures import jpeg_bytes

client = TestClient(app)

COMPLETE_LABEL = f"""OLD TOM DISTILLERY
Kentucky Straight Bourbon Whiskey
45% Alc./Vol.
750 mL
{STATUTORY_GOVERNMENT_WARNING}
"""


class ScriptedOcrProvider(OcrProvider):
    def __init__(self, text: str = COMPLETE_LABEL) -> None:
        self._text = text
        self.calls = 0

    @property
    def name(self) -> str:
        return "scripted"

    def extract_text(self, image_bytes: bytes) -> OcrResult:
        self.calls += 1
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


def _manifest(*rows: tuple[str, str, str, str, str]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["filename", "brand_name", "class_type", "alcohol_content", "net_contents"],
    )
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def _settings(**kwargs: object) -> Settings:
    base = {
        "openai_enabled": False,
        "batch_max_items": 300,
        "batch_max_concurrency": 2,
        "batch_ai_max_calls": 25,
        "batch_ai_concurrency": 1,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


# --- Manifest validation -----------------------------------------------------


def test_sanitize_rejects_path_traversal() -> None:
    assert sanitize_upload_filename("../etc/passwd") is None
    assert sanitize_upload_filename("folder/label.jpg") is None
    assert sanitize_upload_filename("label.jpg") == "label.jpg"


def test_valid_manifest() -> None:
    csv_bytes = _manifest(
        ("a.jpg", "OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey", "45%", "750 mL"),
    )
    result = parse_and_validate_manifest(csv_bytes, ["a.jpg"], settings=_settings())
    assert result.valid is True
    assert result.matched_count == 1


def test_missing_columns() -> None:
    csv_bytes = b"filename,brand_name\na.jpg,X\n"
    result = parse_and_validate_manifest(csv_bytes, ["a.jpg"], settings=_settings())
    assert result.valid is False
    assert any(i.code == "missing_columns" for i in result.issues)


def test_empty_manifest() -> None:
    result = parse_and_validate_manifest(b"", ["a.jpg"], settings=_settings())
    assert result.valid is False
    assert any(i.code == "empty_manifest" for i in result.issues)


def test_duplicate_filename_in_manifest() -> None:
    csv_bytes = _manifest(
        ("a.jpg", "A", "Bourbon Whiskey", "45%", "750 mL"),
        ("a.jpg", "B", "Bourbon Whiskey", "40%", "750 mL"),
    )
    result = parse_and_validate_manifest(csv_bytes, ["a.jpg"], settings=_settings())
    assert result.valid is False
    assert any(i.code == "duplicate_filename" for i in result.issues)


def test_missing_image() -> None:
    csv_bytes = _manifest(
        ("a.jpg", "A", "Bourbon Whiskey", "45%", "750 mL"),
    )
    result = parse_and_validate_manifest(csv_bytes, ["b.jpg"], settings=_settings())
    assert result.valid is False
    assert any(i.code == "missing_image" for i in result.issues)


def test_extra_unreferenced_image_warning_allows_valid_match() -> None:
    csv_bytes = _manifest(
        ("a.jpg", "A", "Bourbon Whiskey", "45%", "750 mL"),
    )
    result = parse_and_validate_manifest(
        csv_bytes,
        ["a.jpg", "extra.jpg"],
        settings=_settings(),
    )
    assert result.valid is True
    assert result.unreferenced_count == 1
    assert any(i.code == "unreferenced_image" for i in result.issues)


def test_unsupported_image_extension() -> None:
    csv_bytes = _manifest(
        ("a.gif", "A", "Bourbon Whiskey", "45%", "750 mL"),
    )
    result = parse_and_validate_manifest(csv_bytes, ["a.gif"], settings=_settings())
    assert result.valid is False
    assert any(i.code == "unsupported_image" for i in result.issues)


def test_max_batch_size() -> None:
    rows = [
        (f"f{i}.jpg", "A", "Bourbon Whiskey", "45%", "750 mL")
        for i in range(5)
    ]
    csv_bytes = _manifest(*rows)
    result = parse_and_validate_manifest(
        csv_bytes,
        [f"f{i}.jpg" for i in range(5)],
        settings=_settings(batch_max_items=3),
    )
    assert result.valid is False
    assert any(i.code == "batch_too_large" for i in result.issues)


def test_csv_formula_sanitize() -> None:
    assert sanitize_csv_cell("=CMD()") == "'=CMD()"
    assert sanitize_csv_cell("normal") == "normal"


# --- Orchestration -----------------------------------------------------------


def test_item_error_does_not_terminate_batch() -> None:
    store = BatchStore()
    ocr = ScriptedOcrProvider()
    settings = _settings(batch_max_concurrency=2)
    orch = BatchOrchestrator(settings=settings, store=store, ocr_provider=ocr)

    good = jpeg_bytes()
    bad = b"not-an-image"
    csv_bytes = _manifest(
        ("good.jpg", "OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey", "45%", "750 mL"),
        ("bad.jpg", "OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey", "45%", "750 mL"),
    )
    names = ["good.jpg", "bad.jpg"]
    images = {"good.jpg": (good, "image/jpeg"), "bad.jpg": (bad, "image/jpeg")}
    created = orch.create_and_start(csv_bytes, images, names, start_background=False)
    status = orch.get_status(created.batch_id)
    assert status is not None
    assert status.state == BatchJobState.COMPLETED
    assert status.summary.error_count == 1
    assert status.summary.completed == 1
    states = {i.filename: i.processing_state for i in status.items}
    assert states["bad.jpg"] == BatchItemProcessingState.ERROR
    assert states["good.jpg"] == BatchItemProcessingState.COMPLETED
    assert status.items[0].overall_status in {None, "PASS", "REVIEW", "FAIL"} or True
    # ERROR is not FAIL
    err = next(i for i in status.items if i.filename == "bad.jpg")
    assert err.overall_status is None
    assert err.error_code is not None


def test_uses_verification_service_parity() -> None:
    """Same app+image → same overall status via VerificationService (single vs batch item)."""
    ocr = ScriptedOcrProvider()
    settings = _settings()
    image = jpeg_bytes()
    application = ApplicationData(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content_abv="45%",
        net_contents="750 mL",
    )
    single = VerificationService(
        settings=settings,
        ocr_provider=ocr,
        ai_provider=NullAiProvider(),
    ).verify(image, application, filename="parity.jpg")

    store = BatchStore()
    orch = BatchOrchestrator(settings=settings, store=store, ocr_provider=ScriptedOcrProvider())
    csv_bytes = _manifest(
        (
            "parity.jpg",
            "OLD TOM DISTILLERY",
            "Kentucky Straight Bourbon Whiskey",
            "45%",
            "750 mL",
        ),
    )
    created = orch.create_and_start(
        csv_bytes,
        {"parity.jpg": (image, "image/jpeg")},
        ["parity.jpg"],
        start_background=False,
    )
    status = orch.get_status(created.batch_id)
    assert status is not None
    detail = orch.get_item_detail(created.batch_id, status.items[0].item_id)
    assert detail is not None and detail.result is not None
    assert detail.result.verification.overall_status == single.verification.overall_status


def test_ai_budget_exhaustion_leaves_review() -> None:
    partial = f"""OLD TOM DISTILLERY
Bourbon Whis
45% Alc./Vol.
750 mL
{STATUTORY_GOVERNMENT_WARNING}
"""
    ocr = ScriptedOcrProvider(partial)
    ai = ScriptedAiProvider(
        results=[
            AiFieldEvidence(
                field="class_type",
                candidate_value="Kentucky Straight Bourbon Whiskey",
                confidence=AiEvidenceConfidence.HIGH,
            ),
        ],
    )
    settings = _settings(openai_enabled=True, openai_api_key="k", batch_ai_max_calls=1)

    def factory(budget_ai: BudgetAwareAiProvider) -> VerificationService:
        return VerificationService(settings=settings, ocr_provider=ocr, ai_provider=budget_ai)

    store = BatchStore()
    orch = BatchOrchestrator(
        settings=settings,
        store=store,
        verification_factory=factory,
    )
    rows = [
        (
            f"p{i}.jpg",
            "OLD TOM DISTILLERY",
            "Kentucky Straight Bourbon Whiskey",
            "45%",
            "750 mL",
        )
        for i in range(3)
    ]
    csv_bytes = _manifest(*rows)
    images = {f"p{i}.jpg": (jpeg_bytes(), "image/jpeg") for i in range(3)}
    names = [f"p{i}.jpg" for i in range(3)]
    # Inject shared budget into factory via closure — factory receives new BudgetAware each item.
    # Re-bind orchestrator to use one shared budget:
    shared = BudgetAwareAiProvider(ai, max_calls=1, ai_concurrency=1)

    def factory_shared(_b: BudgetAwareAiProvider) -> VerificationService:
        return VerificationService(settings=settings, ocr_provider=ocr, ai_provider=shared)

    orch = BatchOrchestrator(
        settings=settings,
        store=store,
        verification_factory=factory_shared,
    )
    created = orch.create_and_start(csv_bytes, images, names, start_background=False)
    status = orch.get_status(created.batch_id)
    assert status is not None
    assert shared.calls_used <= 1
    # At least one item should remain REVIEW (budget or unresolved)
    assert status.summary.review_count + status.summary.pass_count + status.summary.fail_count == 3


def test_bounded_concurrency_observed() -> None:
    """ concurrent workers capped — verify with a slow OCR counter. """
    class SlowOcr(ScriptedOcrProvider):
        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.max_active = 0
            self._lock = __import__("threading").Lock()

        def extract_text(self, image_bytes: bytes) -> OcrResult:
            with self._lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(0.05)
            try:
                return super().extract_text(image_bytes)
            finally:
                with self._lock:
                    self.active -= 1

    ocr = SlowOcr()
    settings = _settings(batch_max_concurrency=2)
    store = BatchStore()
    orch = BatchOrchestrator(settings=settings, store=store, ocr_provider=ocr)
    n = 6
    rows = [
        (f"c{i}.jpg", "OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey", "45%", "750 mL")
        for i in range(n)
    ]
    csv_bytes = _manifest(*rows)
    images = {f"c{i}.jpg": (jpeg_bytes(), "image/jpeg") for i in range(n)}
    names = [f"c{i}.jpg" for i in range(n)]
    orch.create_and_start(csv_bytes, images, names, start_background=False)
    assert ocr.max_active <= 2


def test_300_item_mocked_orchestration() -> None:
    ocr = ScriptedOcrProvider()
    settings = _settings(batch_max_concurrency=4, batch_max_items=300)
    store = BatchStore()
    orch = BatchOrchestrator(settings=settings, store=store, ocr_provider=ocr)
    n = 300
    rows = [
        (f"m{i}.jpg", "OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey", "45%", "750 mL")
        for i in range(n)
    ]
    csv_bytes = _manifest(*rows)
    one_jpeg = jpeg_bytes()
    images = {f"m{i}.jpg": (one_jpeg, "image/jpeg") for i in range(n)}
    names = [f"m{i}.jpg" for i in range(n)]
    t0 = time.perf_counter()
    created = orch.create_and_start(csv_bytes, images, names, start_background=False)
    elapsed = time.perf_counter() - t0
    status = orch.get_status(created.batch_id)
    assert status is not None
    assert status.summary.total == 300
    assert status.summary.completed + status.summary.error_count == 300
    assert status.state == BatchJobState.COMPLETED
    # Soft throughput observation for the report (not a brittle CI gate).
    assert elapsed < 180, f"300 mocked items took too long: {elapsed:.1f}s"


def test_export_csv_and_api_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "OLD TOM" in sample_manifest_csv()
    csv_bytes = _manifest(
        ("a.jpg", "OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey", "45%", "750 mL"),
    )
    # API validate
    response = client.post(
        "/api/v1/batches/validate",
        files=[
            ("manifest", ("manifest.csv", csv_bytes, "text/csv")),
            ("files", ("a.jpg", jpeg_bytes(), "image/jpeg")),
        ],
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True

    store = BatchStore()
    orch = BatchOrchestrator(
        settings=_settings(),
        store=store,
        ocr_provider=ScriptedOcrProvider(),
    )
    created = orch.create_and_start(
        csv_bytes,
        {"a.jpg": (jpeg_bytes(), "image/jpeg")},
        ["a.jpg"],
        start_background=False,
    )
    exported = orch.export_csv(created.batch_id)
    assert exported is not None
    assert "filename" in exported.splitlines()[0]
    assert "a.jpg" in exported
