"""Runtime settings loader (Milestone 1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config.defaults import DEFAULT_DATA_DIR, DEFAULT_DB_FILENAME


@dataclass(slots=True)
class AppSettings:
    database_path: Path


def load_settings() -> AppSettings:
    data_dir = DEFAULT_DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / DEFAULT_DB_FILENAME
    return AppSettings(database_path=db_path)
