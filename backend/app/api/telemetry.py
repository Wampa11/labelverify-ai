"""
Lightweight operational telemetry endpoints.

Architectural responsibility: record privacy-safe site-access events for
Docker log inspection. Never accepts or logs label content.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.audit import SITE_ACCESS, emit_audit_event
from app.core.config import get_settings
from app.core.request_context import get_request_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


class AccessTelemetryRequest(BaseModel):
    """Optional client context for site_access (no PII / fingerprints)."""

    route: str | None = Field(
        default=None,
        max_length=64,
        description="Logical UI route, e.g. workspace or how-it-works",
    )


class AccessTelemetryResponse(BaseModel):
    """Ack only — telemetry must never drive UI behavior."""

    recorded: bool = True


_DEFAULT_ACCESS_BODY = AccessTelemetryRequest()


@router.post(
    "/access",
    response_model=AccessTelemetryResponse,
    summary="Record a privacy-safe site access event",
    description=(
        "Called once per SPA load. Emits a site_access audit log line. "
        "Does not store analytics or accept label content."
    ),
)
async def record_site_access(
    request: Request,
    body: AccessTelemetryRequest | None = None,
) -> AccessTelemetryResponse:
    """Log that the deployed UI was loaded; never raise to callers on log failure."""
    payload = body if body is not None else _DEFAULT_ACCESS_BODY
    try:
        request_id = get_request_id() or getattr(request.state, "request_id", None)
        emit_audit_event(
            SITE_ACCESS,
            request_id=request_id,
            route=payload.route or "app",
            app_version=get_settings().app_version,
        )
        return AccessTelemetryResponse(recorded=True)
    except Exception:  # noqa: BLE001 — telemetry must not break the SPA
        logger.exception("site_access_telemetry_failed")
        return AccessTelemetryResponse(recorded=False)
