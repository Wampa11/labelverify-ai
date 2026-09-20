"""
AI provider factory.

Architectural responsibility: construct providers from settings without leaking
OpenAI types into callers.
"""

from __future__ import annotations

from app.ai.null_provider import NullAiProvider
from app.ai.openai_provider import OpenAiProvider
from app.ai.provider import AiAvailability, AiProvider
from app.core.config import Settings, get_settings


def create_ai_provider(settings: Settings | None = None) -> AiProvider:
    """
    Build the configured AI provider.

    Disabled by default. Missing key with OPENAI_ENABLED=true → unavailable null provider.
    """
    cfg = settings or get_settings()
    if not cfg.openai_enabled:
        return NullAiProvider(reason="OPENAI_ENABLED=false")
    if not cfg.openai_api_key:
        return NullAiProvider(
            reason="OPENAI_ENABLED=true but OPENAI_API_KEY is missing",
            availability=AiAvailability.UNAVAILABLE,
        )
    return OpenAiProvider(
        api_key=cfg.openai_api_key,
        model=cfg.openai_model,
        timeout_seconds=cfg.openai_timeout_seconds,
    )
