"""
Health, liveness, and readiness endpoints.

Architectural responsibility: deployment probes — OpenAI is optional and never required for ready.
"""

from __future__ import annotations

import logging
import shutil

from fastapi import APIRouter, Response, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


def openai_fallback_status(settings=None) -> dict[str, object]:
    """Safe OpenAI configuration summary — never includes the API key."""
    cfg = settings or get_settings()
    key_present = bool(cfg.openai_api_key)
    configured = bool(cfg.openai_enabled) and key_present
    if not cfg.openai_enabled:
        label = "not configured"
        detail = "OPENAI_ENABLED=false"
    elif not key_present:
        label = "enabled but missing API key"
        detail = "OPENAI_ENABLED=true; OPENAI_API_KEY unset"
    else:
        label = "configured/enabled"
        detail = f"model={cfg.openai_model}"
    return {
        "openai_fallback": label,
        "openai_enabled": cfg.openai_enabled,
        "openai_api_key_present": key_present,
        "openai_configured": configured,
        "openai_model": cfg.openai_model if cfg.openai_enabled else None,
        "detail": detail,
    }


def log_openai_fallback_status(settings=None) -> None:
    """Startup/diagnostic log line for developers (no secrets)."""
    status_info = openai_fallback_status(settings)
    if status_info["openai_configured"]:
        logger.info(
            "OpenAI fallback: configured/enabled | Model: %s",
            status_info["openai_model"],
        )
    else:
        logger.info("OpenAI fallback: not configured (%s)", status_info["detail"])


@router.get("/health")
def health_check() -> dict[str, object]:
    """Compatibility health payload (alive + config flags; not a secret)."""
    settings = get_settings()
    openai = openai_fallback_status(settings)
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "openai_enabled": settings.openai_enabled,
        "openai_configured": openai["openai_configured"],
        "openai_fallback": openai["openai_fallback"],
        "openai_model": openai["openai_model"],
        "ocr_provider": settings.ocr_provider,
        "app_env": settings.app_env,
    }


@router.get("/health/live")
def liveness() -> dict[str, str]:
    """Process is up (Docker HEALTHCHECK / liveness probe)."""
    return {"status": "alive"}


@router.get("/ready")
def readiness(response: Response) -> dict[str, object]:
    """
    Ready to serve verification requests.

    Checks local OCR binary when provider is tesseract. Does NOT require OpenAI.
    """
    settings = get_settings()
    openai = openai_fallback_status(settings)
    checks: dict[str, object] = {
        "app": True,
        "openai_required": False,
        "openai_enabled": settings.openai_enabled,
        "openai_configured": openai["openai_configured"],
        "openai_fallback": openai["openai_fallback"],
        "openai_model": openai["openai_model"],
    }
    ready = True

    if settings.ocr_provider == "tesseract":
        tesseract_path = shutil.which("tesseract")
        checks["tesseract"] = bool(tesseract_path)
        if not tesseract_path:
            ready = False
            checks["tesseract_detail"] = "tesseract binary not found on PATH"
    else:
        checks["tesseract"] = "skipped"

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "version": settings.app_version,
            "checks": checks,
        }

    return {
        "status": "ready",
        "version": settings.app_version,
        "checks": checks,
    }
