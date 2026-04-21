from __future__ import annotations

from tgx_automation.adb_client import AdbClient
from tgx_automation.ui_xml import find_node_by_resource, find_node_by_text


def _clear_focused_field(adb: AdbClient, max_chars: int = 80) -> None:
    adb.keyevent(123)
    for _ in range(max_chars):
        adb.keyevent(67)


def _tap_done(adb: AdbClient, fallback: tuple[int, int]) -> str:
    xml = adb.dump_ui_xml()
    done = find_node_by_resource(xml, ["btn_done"])
    if done and done.center:
        adb.tap(*done.center)
        return "submit via btn_done"
    adb.tap(*fallback)
    return "submit via fallback"


def click_start_messaging(adb: AdbClient) -> str:
    xml = adb.dump_ui_xml()
    node = find_node_by_text(xml, ["start messaging"])
    if not node:
        node = find_node_by_resource(xml, ["btn_done"])

    if node and node.center:
        adb.tap(*node.center)
        return "clicked start messaging"

    # fallback only when marker exists but button parse failed
    if "start messaging" in xml.lower():
        adb.tap(360, 1104)
        return "clicked start messaging (fallback)"

    return "start messaging not found"


def fill_phone(adb: AdbClient, country: str, code: str, phone: str) -> list[str]:
    steps = []
    if country:
        steps.append("skip country; Telegram X derives country from the dial code")

    adb.tap(120, 396)
    _clear_focused_field(adb, 8)
    adb.input_text(code)
    steps.append("set code")

    adb.tap(470, 396)
    _clear_focused_field(adb, 32)
    adb.input_text(phone)
    steps.append("set phone")

    steps.append(_tap_done(adb, (632, 650)))
    return steps


def submit_code(adb: AdbClient, code: str) -> list[str]:
    adb.tap(360, 369)
    _clear_focused_field(adb, 16)
    adb.input_text(code)
    return ["input code"]


def submit_password(adb: AdbClient, password: str) -> list[str]:
    adb.tap(360, 369)
    _clear_focused_field(adb, 96)
    adb.input_text(password)
    return ["clear password field", "input password", _tap_done(adb, (594, 612))]


def submit_current_text(adb: AdbClient, value: str, label: str = "value") -> list[str]:
    adb.tap(360, 369)
    _clear_focused_field(adb, 96)
    adb.input_text(value)
    adb.keyevent(66)
    return [f"input {label}", "keyboard done"]
