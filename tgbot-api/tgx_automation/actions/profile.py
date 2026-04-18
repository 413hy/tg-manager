from __future__ import annotations

from tgx_automation.adb_client import AdbClient


def open_settings(adb: AdbClient) -> str:
    adb.open_deeplink("tg://settings")
    return "open settings"


def open_username_editor(adb: AdbClient) -> list[str]:
    steps = []
    adb.tap(360, 616)
    steps.append("tap btn_username")
    # fallback overlay button if present in this build
    adb.tap(632, 512)
    steps.append("tap username overlay/fab")
    return steps


def change_username(adb: AdbClient, username: str) -> list[str]:
    steps = []
    adb.tap(360, 272)
    adb.keyevent(123)
    for _ in range(24):
        adb.keyevent(67)
    adb.input_text(username)
    steps.append(f"typed username={username}")
    adb.keyevent(66)
    steps.append("keyboard done")
    return steps


def change_name(adb: AdbClient, first_name: str, last_name: str) -> list[str]:
    steps = []
    adb.open_deeplink("tg://settings")
    adb.tap(632, 512)
    steps.append("open profile edit")

    adb.tap(220, 272)
    adb.keyevent(123)
    for _ in range(24):
        adb.keyevent(67)
    adb.input_text(first_name)
    steps.append("set first name")

    adb.tap(520, 272)
    adb.keyevent(123)
    for _ in range(24):
        adb.keyevent(67)
    adb.input_text(last_name)
    steps.append("set last name")

    adb.tap(600, 520)
    steps.append("submit profile")
    return steps
