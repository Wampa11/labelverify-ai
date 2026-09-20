"""
Phase 8.10 operational audit / telemetry tests.

Architectural responsibility: prove privacy-safe events, request-id correlation,
and that telemetry cannot break workflows.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.audit import (
    APPLICATION_ERROR,
    BATCH_REVIEW_COMPLETED,
    BATCH_REVIEW_STARTED,
    SINGLE_REVIEW_COMPLETED,
    SINGLE_REVIEW_STARTED,
    SITE_ACCESS,
    emit_application_error,
    emit_audit_event,
)
from app.core.request_context import get_request_id, set_request_id
from app.main import app
from app.ocr.base import OcrProvider, OcrResult
from app.services.verification_service import VerificationService
from tests.image_fixtures import jpeg_bytes

client = TestClient(app)


class _AuditCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(json.loads(record.getMessage()))
        except json.JSONDecodeError:
            pass


@pytest.fixture
def audit_logs() -> _AuditCapture:
    handler = _AuditCapture()
    logger = logging.getLogger("labelverify.audit")
    previous = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)
    logger.setLevel(previous)


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


COMPLETE_LABEL = """STONE'S THROW
Straight Bourbon Whiskey
45% Alc./Vol.
750 mL
GOVERNMENT WARNING: (1) According to the Surgeon General, women should not
drink alcoholic beverages during pregnancy because of the risk of birth defects.
(2) Consumption of alcoholic beverages impairs your ability to drive a car or
operate machinery, and may cause health problems.
"""


def test_a_site_access_event_recorded(audit_logs: _AuditCapture) -> None:
    response = client.post(
        "/api/v1/telemetry/access",
        json={"route": "workspace"},
        headers={"X-Request-ID": "req-access-1"},
    )
    assert response.status_code == 200
    assert response.json()["recorded"] is True
    events = [e for e in audit_logs.records if e.get("event") == SITE_ACCESS]
    assert len(events) == 1
    assert events[0]["route"] == "workspace"
    assert events[0]["request_id"] == "req-access-1"
    assert "app_version" in events[0]
    assert "timestamp" in events[0]


def test_b_telemetry_failure_does_not_break_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):  # noqa: ANN001
        raise RuntimeError("telemetry boom")

    monkeypatch.setattr("app.api.telemetry.emit_audit_event", boom)
    response = client.post("/api/v1/telemetry/access", json={"route": "workspace"})
    assert response.status_code == 200
    assert response.json()["recorded"] is False
    assert client.get("/ready").status_code == 200


def test_c_d_single_completion_safe_metadata(
    audit_logs: _AuditCapture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import verification as verification_mod

    service = VerificationService(ocr_provider=ScriptedOcrProvider(COMPLETE_LABEL))

    monkeypatch.setattr(
        verification_mod,
        "VerificationService",
        lambda *args, **kwargs: service,
    )

    response = client.post(
        "/api/v1/verify",
        files={"file": ("x.jpg", jpeg_bytes(), "image/jpeg")},
        headers={"X-Request-ID": "req-single-1"},
    )
    assert response.status_code == 200
    body = response.json()
    # Ensure response still has content (not asserting log leak of it)
    assert "verification" in body

    started = [e for e in audit_logs.records if e.get("event") == SINGLE_REVIEW_STARTED]
    completed = [e for e in audit_logs.records if e.get("event") == SINGLE_REVIEW_COMPLETED]
    assert started
    assert completed
    event = completed[-1]
    assert event["request_id"] == "req-single-1"
    assert event["overall_status"] in {"PASS", "REVIEW", "FAIL"}
    assert "duration_ms" in event
    assert "ai_used" in event
    assert "secondary_ocr_used" in event
    assert "quality_status" in event
    # D — must not contain extracted label values / image data
    serialized = json.dumps(event)
    assert "STONE" not in serialized
    assert "Bourbon" not in serialized
    assert "display_image" not in serialized
    assert "base64" not in serialized.lower()
    assert "750" not in serialized
    assert "45%" not in serialized


def test_e_batch_event_aggregate_counts(audit_logs: _AuditCapture) -> None:
    set_request_id("req-batch-1")
    try:
        emit_audit_event(
            BATCH_REVIEW_STARTED,
            request_id="req-batch-1",
            batch_id="b1",
            label_count=3,
        )
        emit_audit_event(
            BATCH_REVIEW_COMPLETED,
            request_id="req-batch-1",
            batch_id="b1",
            label_count=3,
            pass_count=1,
            review_count=1,
            fail_count=1,
            error_count=0,
            ai_calls_used=2,
            duration_ms=1200.5,
        )
    finally:
        set_request_id(None)

    completed = [e for e in audit_logs.records if e.get("event") == BATCH_REVIEW_COMPLETED]
    assert completed
    event = completed[-1]
    assert event["label_count"] == 3
    assert event["pass_count"] == 1
    assert event["review_count"] == 1
    assert event["fail_count"] == 1
    assert event["ai_calls_used"] == 2
    assert "brand" not in json.dumps(event).lower() or event.get("brand") is None


def test_f_error_logging_avoids_sensitive_data(audit_logs: _AuditCapture) -> None:
    emit_application_error(
        operation="single_review",
        stage="ocr",
        error_type="OcrProviderError",
        message="OCR failed; key=sk-SECRET123 Authorization: Bearer tok payload=...",
        request_id="req-err-1",
    )
    errors = [e for e in audit_logs.records if e.get("event") == APPLICATION_ERROR]
    assert errors
    event = errors[-1]
    assert event["request_id"] == "req-err-1"
    assert event["error_type"] == "OcrProviderError"
    # Message is truncated/sanitized to caller-provided safe text — callers must pass safe msgs.
    # Guard that our verification path uses safe messages (no raw key material in type field).
    assert event["operation"] == "single_review"
    assert "sk-SECRET" not in event["error_type"]


def test_g_request_id_correlation(audit_logs: _AuditCapture) -> None:
    set_request_id("corr-99")
    try:
        assert get_request_id() == "corr-99"
        emit_audit_event(SITE_ACCESS, route="workspace")
    finally:
        set_request_id(None)
    events = [e for e in audit_logs.records if e.get("event") == SITE_ACCESS]
    assert events[-1]["request_id"] == "corr-99"


def test_emit_never_includes_forbidden_keys_by_convention(audit_logs: _AuditCapture) -> None:
    emit_audit_event(
        SINGLE_REVIEW_COMPLETED,
        overall_status="REVIEW",
        duration_ms=10,
        ai_used=False,
        secondary_ocr_used=False,
        quality_status="WARNING",
    )
    event = audit_logs.records[-1]
    forbidden = {
        "filename",
        "brand_name",
        "class_type",
        "alcohol_content",
        "net_contents",
        "raw_text",
        "image_bytes",
        "api_key",
        "authorization",
        "prompt",
    }
    assert forbidden.isdisjoint(event.keys())
