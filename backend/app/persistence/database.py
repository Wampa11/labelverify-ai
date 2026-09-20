"""
SQLite database bootstrap skeleton.

Architectural responsibility: connection/setup for local prototype persistence.
"""

from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import NotImplementedStageError


class Database:
    """SQLite gateway. Schema and migrations arrive in a later phase."""

    def __init__(self, database_url: str | None = None) -> None:
        settings = get_settings()
        self.database_url = database_url or settings.database_url

    def ensure_data_directory(self) -> Path:
        """Create the local data directory for SQLite/uploads when using a relative file URL."""
        if self.database_url.startswith("sqlite:///./"):
            relative = self.database_url.removeprefix("sqlite:///./")
            path = Path(relative).parent
            path.mkdir(parents=True, exist_ok=True)
            return path
        return Path(".")

    def connect(self) -> None:
        """Open a connection. Not fully implemented in Phase 1."""
        self.ensure_data_directory()
        raise NotImplementedStageError(
            "SQLite persistence is not fully implemented in Phase 1",
            details=f"database_url={self.database_url!r}",
        )
