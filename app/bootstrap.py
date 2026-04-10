"""App bootstrap orchestration for Milestone 1."""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import AppSettings, load_settings
from app.infrastructure.db.engine import Database


@dataclass(slots=True)
class AppContext:
    """Shared process context passed to UI/services during startup."""

    settings: AppSettings
    database: Database


def bootstrap_app() -> AppContext:
    """Load settings and initialize local SQLite schema."""
    settings = load_settings()
    database = Database(settings.database_path)
    database.initialize_schema()
    return AppContext(settings=settings, database=database)
