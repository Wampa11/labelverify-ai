"""
Application configuration loaded from environment variables.

Architectural responsibility: typed settings for the backend; never expose secrets to the frontend.

Local development loads ``backend/.env`` (path resolved from this package).
Operating-system / container environment variables always override dotenv values.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py → backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ENV_FILE = _BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    """Runtime configuration for the LabelVerify AI backend."""

    model_config = SettingsConfigDict(
        # Absolute path so local uvicorn works regardless of shell cwd.
        env_file=_BACKEND_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        # Default pydantic-settings priority: init > env > dotenv.
        # Runtime OS/container env therefore overrides backend/.env.
    )

    app_name: str = "LabelVerify AI"
    app_env: str = "development"
    app_version: str = "0.8.0"
    log_level: str = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    database_url: str = "sqlite:///./data/labelverify.db"
    upload_dir: str = "./data/uploads"

    # Phase 7 batch orchestration (local prototype; in-memory jobs)
    batch_max_items: int = 300
    batch_max_concurrency: int = 2
    batch_ai_max_calls: int = 25
    batch_ai_concurrency: int = 1

    openai_enabled: bool = False
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 8.0
    openai_max_calls_per_review: int = 1
    openai_max_image_edge_px: int = 1280

    # Production OCR (Phase 3 selection / Phase 4 wiring)
    ocr_provider: str = "tesseract"
    ocr_preprocess_profile: str = "fast"
    ocr_fast_max_edge_px: int = 1600
    ocr_enhanced_max_edge_px: int = 1200

    # Phase 8.9 selective brand OCR escalation
    brand_region_ocr_enabled: bool = True
    secondary_ocr_enabled: bool = False
    secondary_ocr_provider: str = "rapidocr"

    # Phase 5 fuzzy / numeric comparison heuristics (engineering — see ADR-019)
    brand_pass_ratio: float = 95.0
    brand_review_ratio: float = 85.0
    class_pass_ratio: float = 97.0
    abv_compare_epsilon: float = 0.05
    net_contents_epsilon_ml: float = 0.5

    # Image upload / preprocessing limits (engineering heuristics — see docs/PERFORMANCE.md)
    max_upload_bytes: int = 15 * 1024 * 1024
    max_image_dimension_px: int = 8000
    min_image_dimension_px: int = 100
    display_max_edge_px: int = 2400
    # Phase 2 display-pipeline OCR preview working image (not the production FAST path)
    ocr_preview_max_edge_px: int = 2200

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
