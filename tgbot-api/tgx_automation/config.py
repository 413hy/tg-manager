from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    adb_serial: str = os.getenv("ADB_SERIAL", "127.0.0.1:5555")
    telegram_bot_token: str = os.getenv(
        "TELEGRAM_BOT_TOKEN",
        "8555605888:AAHFKMN7UyK2C9u-rarCq5PbPQAexVHbdOA",
    )


settings = Settings()
