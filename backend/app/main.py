"""
FastAPI application entrypoint for LabelVerify AI.

Architectural responsibility: compose the HTTP app, middleware, and routers — not business rules.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.request_context import set_request_id

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request IDs and safe timing logs (no secrets / payloads)."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        set_request_id(request_id)
        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
            elapsed_ms = (time.perf_counter() - started) * 1000
            response.headers["X-Request-ID"] = request_id
            response.headers["X-App-Version"] = get_settings().app_version
            # Avoid logging Authorization or bodies.
            logger.info(
                "http_request request_id=%s method=%s path=%s status=%s elapsed_ms=%.1f",
                request_id,
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            return response
        finally:
            set_request_id(None)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add conservative security headers on API responses."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response


def create_app() -> FastAPI:
    """Build and return the FastAPI application instance."""
    settings = get_settings()
    from app.api.health import log_openai_fallback_status

    log_openai_fallback_status(settings)
    docs_url = None if settings.app_env == "production" else "/docs"
    redoc_url = None if settings.app_env == "production" else "/redoc"
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "LabelVerify AI prototype API. Decision support only — "
            "does not make final regulatory determinations."
        ),
        docs_url=docs_url,
        redoc_url=redoc_url,
    )
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    application.include_router(api_router)
    return application


app = create_app()
