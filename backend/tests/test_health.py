"""
Health endpoint tests.

Architectural responsibility: verify liveness/readiness wiring; OpenAI never required for ready.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    """Health endpoint should report ok and expose non-secret flags."""
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "openai_enabled" in payload
    assert "ocr_provider" in payload
    assert "version" in payload


def test_liveness() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_readiness_does_not_require_openai() -> None:
    response = client.get("/ready")
    assert response.status_code in {200, 503}
    payload = response.json()
    assert payload["checks"]["openai_required"] is False
    assert "version" in payload
