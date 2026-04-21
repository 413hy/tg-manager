from __future__ import annotations

from tgx_automation.adb_client import AdbClient
from tgx_automation.ui_xml import find_node_by_resource, find_node_by_text


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
    adb.keyevent(123)
    for _ in range(4):
        adb.keyevent(67)
    adb.input_text(code)
    steps.append("set code")

    adb.tap(470, 396)
    adb.input_text(phone)
    steps.append("set phone")

    xml = adb.dump_ui_xml()
    done = find_node_by_resource(xml, ["btn_done"])
    if done and done.center:
        adb.tap(*done.center)
        steps.append("submit phone")
    else:
        adb.tap(632, 650)
        steps.append("submit phone (fallback)")
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


def submit_current_text(adb: AdbClient, value: str, label: str = "value") -> list[str]:
    adb.tap(360, 369)
    adb.input_text(value)
    adb.keyevent(66)
    return [f"input {label}", "keyboard done"]
