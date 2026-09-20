"""
Request-scoped correlation helpers for operational audit logs.

Architectural responsibility: propagate request_id via contextvars without
coupling domain services to FastAPI Request objects.
"""

from __future__ import annotations

from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("labelverify_request_id", default=None)


def set_request_id(request_id: str | None) -> None:
    """Bind the active HTTP request id for the current context."""
    _request_id.set(request_id)


def get_request_id() -> str | None:
    """Return the bound request id, if any."""
    return _request_id.get()
