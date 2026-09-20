"""
Optional AI assistance for ambiguous extraction/interpretation.

Architectural responsibility: provider abstraction + evidence recovery adapters.
OpenAI SDK/HTTP details stay in openai_provider.py only.
"""

from app.ai.factory import create_ai_provider
from app.ai.null_provider import NullAiProvider
from app.ai.provider import AiAvailability, AiProvider

__all__ = [
    "AiAvailability",
    "AiProvider",
    "NullAiProvider",
    "create_ai_provider",
]
