from __future__ import annotations

import time

from tgx_automation.adb_client import AdbClient
from tgx_automation.ui_xml import find_node_by_resource, find_node_by_text, parse_nodes


def _clear_focused_field(adb: AdbClient, max_chars: int = 80) -> None:
    adb.keyevent(123)
    for _ in range(4):
        adb.shell("input keyevent --longpress 67")
        time.sleep(0.1)
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


def _tap_resource(adb: AdbClient, xml: str, resource: str, fallback: tuple[int, int]) -> str:
    node = find_node_by_resource(xml, [resource])
    if node and node.center:
        adb.tap(*node.center)
        time.sleep(0.25)
        return f"tap {resource}"
    adb.tap(*fallback)
    time.sleep(0.25)
    return f"tap {resource} fallback"


def _resource_text(xml: str, resource: str) -> str:
    for node in parse_nodes(xml):
        if resource in node.resource_id:
            return node.text
    return ""


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

    xml = adb.dump_ui_xml()
    steps.append(_tap_resource(adb, xml, "login_code", (120, 396)))
    _clear_focused_field(adb, 8)
    adb.input_text(code)
    steps.append("set code")

    # Telegram X renders this field as a custom view; the resource center can
    # keep focus in login_code on some builds. This lower-left point was verified
    # to focus app:id/login_phone on the 720x1184 redroid layout.
    adb.tap(300, 420)
    time.sleep(0.25)
    steps.append("tap login_phone")
    _clear_focused_field(adb, 32)
    adb.input_text(phone)
    steps.append("set phone")

    xml = adb.dump_ui_xml()
    actual_code = _resource_text(xml, "login_code")
    actual_phone = _resource_text(xml, "login_phone")
    if code not in actual_code or phone not in actual_phone:
        raise RuntimeError(
            "phone input verification failed; "
            f"expected_code={code}, actual_code={actual_code or '-'}, "
            f"expected_phone={phone}, actual_phone={actual_phone or '-'}"
        )

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
