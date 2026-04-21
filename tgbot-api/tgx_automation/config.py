from __future__ import annotations

import os
from dataclasses import dataclass, field


def _parse_int_list(value: str) -> tuple[int, ...]:
    ids: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if part:
            ids.append(int(part))
    return tuple(ids)


@dataclass(frozen=True)
class Settings:
    adb_serial: str = os.getenv("ADB_SERIAL", "127.0.0.1:5555")
    redroid_name: str = os.getenv("REDROID_NAME", "redroid12")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    db_path: str = os.getenv("TGX_DB_PATH", "tgx_automation.sqlite3")
    telegram_admin_ids: tuple[int, ...] = field(
        default_factory=lambda: _parse_int_list(os.getenv("TELEGRAM_ADMIN_IDS", ""))
    )


settings = Settings()
