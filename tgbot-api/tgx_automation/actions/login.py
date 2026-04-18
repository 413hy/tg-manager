from __future__ import annotations

from tgx_automation.adb_client import AdbClient


def click_start_messaging(adb: AdbClient) -> str:
    adb.tap(360, 1104)
    return "clicked start messaging"


def fill_phone(adb: AdbClient, country: str, code: str, phone: str) -> list[str]:
    steps = []
    adb.tap(360, 260)
    adb.input_text(country)
    adb.keyevent(66)
    steps.append("set country")

    adb.tap(120, 396)
    adb.keyevent(123)
    for _ in range(4):
        adb.keyevent(67)
    adb.input_text(code)
    steps.append("set code")

    adb.tap(470, 396)
    adb.input_text(phone)
    steps.append("set phone")

    adb.tap(632, 570)
    steps.append("submit phone")
    return steps


def submit_code(adb: AdbClient, code: str) -> list[str]:
    adb.tap(360, 369)
    adb.input_text(code)
    return ["input code"]


def submit_password(adb: AdbClient, password: str) -> list[str]:
    adb.tap(360, 369)
    adb.input_text(password)
    adb.tap(594, 612)
    return ["input password", "submit password"]
