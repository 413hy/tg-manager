from __future__ import annotations

import time

from tgx_automation.adb_client import AdbClient
from tgx_automation.ui_xml import parse_nodes
from tgx_automation.ui_xml import find_node_by_resource, find_node_by_text


def recover_home(adb: AdbClient) -> list[str]:
    steps = []
    for _ in range(3):
        adb.keyevent(4)
        steps.append("back")
    adb.force_stop()
    steps.append("force-stop")
    adb.start_activity("org.thunderdog.challegram/.MainActivity")
    steps.append("start-main")
    return steps


def _tap_resource(adb: AdbClient, xml: str, resource: str) -> bool:
    node = find_node_by_resource(xml, [resource])
    if node and node.center:
        adb.tap(*node.center)
        return True
    return False


def _is_chat_list(xml: str) -> bool:
    return "org.thunderdog.challegram:id/chat" in xml and "msg_list" not in xml


def open_account_switcher(adb: AdbClient) -> tuple[list[str], str]:
    steps: list[str] = []

    adb.start_activity("org.thunderdog.challegram/.MainActivity")
    time.sleep(0.8)
    for _ in range(6):
        xml = adb.dump_ui_xml()
        if _is_chat_list(xml):
            break
        adb.keyevent(4)
        steps.append("back toward chat list")
        time.sleep(0.8)

    adb.tap(56, 104)
    steps.append("open main drawer")
    time.sleep(0.8)

    xml = adb.dump_ui_xml()
    if "btn_addAccount" not in xml:
        adb.tap(546, 289)
        steps.append("expand account switcher")
        time.sleep(0.8)
        xml = adb.dump_ui_xml()

    return steps, xml


def account_switcher_entries(adb: AdbClient) -> tuple[list[str], list[tuple[int, int]]]:
    steps, xml = open_account_switcher(adb)
    centers: list[tuple[int, int]] = []
    for node in parse_nodes(xml):
        if node.resource_id.endswith(":id/account") and node.center:
            centers.append(node.center)
    centers.sort(key=lambda pt: pt[1])
    return steps, centers


def switch_account_by_index(adb: AdbClient, index: int) -> list[str]:
    steps, centers = account_switcher_entries(adb)
    if not centers:
        steps.extend(recover_home(adb))
        retry_steps, centers = account_switcher_entries(adb)
        steps.extend(retry_steps)
    if index < 0 or index >= len(centers):
        raise ValueError(f"account index {index} is out of range; visible accounts={len(centers)}")
    adb.tap(*centers[index])
    steps.append(f"switch account index={index}")
    time.sleep(1.2)
    return steps


def open_add_account(adb: AdbClient) -> list[str]:
    steps, xml = open_account_switcher(adb)

    add_account = find_node_by_resource(xml, ["btn_addAccount"]) or find_node_by_text(xml, ["add account"])
    if add_account and add_account.center:
        adb.tap(*add_account.center)
        steps.append("tap add account")
    else:
        adb.tap(220, 512)
        steps.append("tap add account (fallback)")
    time.sleep(1.0)

    return steps
