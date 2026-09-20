"""
Privacy-conscious operational / audit event logging.

Architectural responsibility: emit one-line structured JSON events to stdout
for Docker log inspection. Never log images, label text, secrets, or payloads.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.core.request_context import get_request_id

logger = logging.getLogger("labelverify.audit")

# Stable event names (filterable in docker compose logs).
SITE_ACCESS = "site_access"
SINGLE_REVIEW_STARTED = "single_review_started"
SINGLE_REVIEW_COMPLETED = "single_review_completed"
BATCH_REVIEW_STARTED = "batch_review_started"
BATCH_REVIEW_COMPLETED = "batch_review_completed"
APPLICATION_ERROR = "application_error"


def emit_audit_event(event: str, **fields: Any) -> None:
    """
    Emit one structured JSON audit line.

    Only operational metadata. Callers must never pass label content, filenames,
    image bytes, API keys, or request bodies.
    """
    payload: dict[str, Any] = {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        "request_id": fields.pop("request_id", None) or get_request_id(),
        "app_version": get_settings().app_version,
    }
    for key, value in fields.items():
        if value is None:
            continue
        payload[key] = value
    # One-line JSON for docker compose logs filters.
    logger.info("%s", json.dumps(payload, separators=(",", ":"), default=str))


def emit_application_error(
    *,
    operation: str,
    error_type: str,
    message: str,
    request_id: str | None = None,
    stage: str | None = None,
) -> None:
    """Log a safe operational error (no secrets / payloads)."""
    # Truncate and strip accidental multiline dumps.
    safe = " ".join(str(message).split())[:240]
    emit_audit_event(
        APPLICATION_ERROR,
        request_id=request_id,
        operation=operation,
        stage=stage or operation,
        error_type=error_type,
        message=safe,
    )
