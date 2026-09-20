"""
Configuration / dotenv loading tests (no real secrets).

Architectural responsibility: prove backend/.env path resolution and empty-key safety.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import _BACKEND_ENV_FILE, Settings, get_settings
from app.main import app


def test_backend_env_file_points_at_backend_dotenv() -> None:
    assert _BACKEND_ENV_FILE.name == ".env"
    assert _BACKEND_ENV_FILE.parent.name == "backend"
    assert _BACKEND_ENV_FILE.parent == Path(__file__).resolve().parents[1]


def test_empty_openai_key_is_not_configured(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    try:
        settings = Settings()
        assert settings.openai_enabled is True
        assert not settings.openai_api_key
        from app.api.health import openai_fallback_status

        status = openai_fallback_status(settings)
        assert status["openai_configured"] is False
        assert status["openai_enabled"] is True
        assert status["openai_model"] == settings.openai_model
    finally:
        get_settings.cache_clear()


def test_health_never_echoes_api_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        payload = client.get("/health").json()
        ready = client.get("/ready")
        assert ready.status_code == 200 or ready.status_code == 503
        blob = str(payload).lower()
        assert "sk-" not in blob
        assert "authorization" not in blob
        assert "openai_configured" in payload
        assert "openai_fallback" in payload
    finally:
        get_settings.cache_clear()


def test_os_env_overrides_dotenv_defaults(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test-override")
    get_settings.cache_clear()
    try:
        settings = Settings()
        assert settings.openai_model == "gpt-test-override"
    finally:
        get_settings.cache_clear()
