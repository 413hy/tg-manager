#!/usr/bin/env python3
from __future__ import annotations

import os
from dataclasses import dataclass


PROJECT_DIR = os.environ.get("PROJECT_DIR", "/root/redroid")
ENV_FILE = os.environ.get("ENV_FILE", os.path.join(PROJECT_DIR, "redroid.env"))


def load_env_file(path: str = ENV_FILE) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Config:
    project_dir: str
    bot_token: str
    allowed_user_id: int
    db_path: str
    poll_timeout: int
    appium_url: str
    adb_serial: str
    app_package: str = "org.thunderdog.challegram"
    app_activity: str = ".MainActivity"


def get_config() -> Config:
    load_env_file()
    token = os.environ.get("TG_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TG_BOT_TOKEN is not configured")

    allowed = os.environ.get("TG_BOT_ALLOWED_USER_ID", "")
    if not allowed:
        raise RuntimeError("TG_BOT_ALLOWED_USER_ID is not configured")

    bind_addr = os.environ.get("APPIUM_BIND_ADDR", "127.0.0.1")
    appium_port = os.environ.get("APPIUM_PORT", "4723")
    adb_addr = os.environ.get("REDROID_ADB_BIND_ADDR", "127.0.0.1")
    adb_port = os.environ.get("REDROID_HOST_ADB_PORT", "5555")

    return Config(
        project_dir=PROJECT_DIR,
        bot_token=token,
        allowed_user_id=int(allowed),
        db_path=os.environ.get("TG_BOT_DB", "/root/redroid/data/accounts.sqlite3"),
        poll_timeout=int(os.environ.get("TG_BOT_POLL_TIMEOUT", "30")),
        appium_url=f"http://{bind_addr}:{appium_port}",
        adb_serial=f"{adb_addr}:{adb_port}",
    )
