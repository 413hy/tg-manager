from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from tgx_automation.actions.interstitial import handle_common_interstitials
from tgx_automation.actions.navigation import recover_home
from tgx_automation.adb_client import AdbClient
from tgx_automation.ui_xml import find_node_by_resource, parse_nodes


def check_spambot_status(adb: AdbClient, work_dir: Path) -> dict:
    steps: list[str] = []
    steps.extend(recover_home(adb))
    steps.extend(handle_common_interstitials(adb))
    steps.extend(_open_spambot(adb, work_dir))
    steps.extend(_send_start(adb))
    steps.extend(_confirm_status_prompt(adb))
    screenshot = work_dir / "spambot-status.png"
    adb.screenshot(screenshot)
    text = _ocr(screenshot)
    result = _classify_spambot_text(text)
    result["steps"] = steps
    result["ocr_text"] = text
    result["screenshot"] = str(screenshot)
    return result


def _open_spambot(adb: AdbClient, work_dir: Path) -> list[str]:
    steps: list[str] = []
    steps.extend(_try_visible_chat_candidates(adb, work_dir))
    if _is_spambot_view(adb, work_dir, "visible"):
        return steps

    adb.shell("am start -a android.intent.action.VIEW -d 'tg://resolve?domain=SpamBot' org.thunderdog.challegram")
    steps.append("open SpamBot deeplink")
    time.sleep(2)
    if _is_spambot_view(adb, work_dir, "deeplink"):
        return steps

    _open_search(adb)
    steps.append("tap search")
    time.sleep(0.5)
    adb.input_text("SpamBot")
    steps.append("search SpamBot")
    time.sleep(1.5)
    steps.extend(handle_common_interstitials(adb))
    if _tap_search_result(adb):
        steps.append("open search result candidate")
        time.sleep(2)
        if _is_spambot_view(adb, work_dir, "search"):
            return steps

    steps.extend(_try_visible_chat_candidates(adb, work_dir))
    if not _is_spambot_view(adb, work_dir, "fallback"):
        raise RuntimeError("failed to open SpamBot chat")
    return steps


def _send_start(adb: AdbClient) -> list[str]:
    xml = adb.dump_ui_xml()
    input_node = find_node_by_resource(xml, ["msg_input"])
    if not input_node or "/start" not in input_node.text:
        if input_node and input_node.center:
            adb.tap(*input_node.center)
        else:
            adb.tap(260, 1135)
        time.sleep(0.2)
        adb.input_text("/start")
    time.sleep(0.2)
    _tap_send(adb)
    time.sleep(4)
    return ["send /start to SpamBot"]


def _tap_send(adb: AdbClient) -> None:
    send_node = find_node_by_resource(adb.dump_ui_xml(), ["msg_send"])
    if send_node and send_node.center:
        adb.tap(*send_node.center)
        time.sleep(0.5)
    if _input_has_start(adb):
        adb.tap(670, 1135)


def _input_has_start(adb: AdbClient) -> bool:
    input_node = find_node_by_resource(adb.dump_ui_xml(), ["msg_input"])
    return bool(input_node and "/start" in input_node.text)


def _confirm_status_prompt(adb: AdbClient) -> list[str]:
    xml = adb.dump_ui_xml()
    for node in parse_nodes(xml):
        if node.text.strip().lower() == "yes" and node.center:
            adb.tap(*node.center)
            time.sleep(5)
            return ["confirm SpamBot status check"]
    return []


def _open_search(adb: AdbClient) -> None:
    xml = adb.dump_ui_xml()
    search_field = next((node for node in parse_nodes(xml) if node.text == "Search"), None)
    if search_field and search_field.center:
        adb.tap(*search_field.center)
        return
    search_button = find_node_by_resource(xml, ["menu_btn_search"])
    if search_button and search_button.center:
        adb.tap(*search_button.center)
        return
    adb.tap(671, 104)


def _tap_search_result(adb: AdbClient) -> bool:
    xml = adb.dump_ui_xml()
    for resource in ("search_chat_local", "search_chat_top"):
        node = find_node_by_resource(xml, [resource])
        if node and node.center:
            adb.tap(*node.center)
            return True
    for node in parse_nodes(xml):
        if node.clickable and node.center:
            x, y = node.center
            if 180 <= y <= 460 and x >= 60:
                adb.tap(x, y)
                return True
    return False


def _try_visible_chat_candidates(adb: AdbClient, work_dir: Path) -> list[str]:
    steps: list[str] = []
    for _ in range(3):
        if "org.thunderdog.challegram:id/chat" in adb.dump_ui_xml():
            break
        adb.keyevent(4)
        steps.append("back to chat list")
        time.sleep(0.7)

    for index, y in enumerate((238, 395, 552, 709), start=1):
        adb.tap(300, y)
        steps.append(f"open visible chat candidate {index}")
        time.sleep(1.6)
        if _is_spambot_view(adb, work_dir, f"candidate-{index}"):
            return steps
        adb.keyevent(4)
        steps.append(f"candidate {index} is not SpamBot")
        time.sleep(0.7)
    return steps


def _is_spambot_view(adb: AdbClient, work_dir: Path, label: str) -> bool:
    if not _is_message_view(adb):
        return False
    screenshot = work_dir / f"spambot-open-{label}.png"
    adb.screenshot(screenshot)
    text = _ocr(screenshot).lower()
    return any(
        marker in text
        for marker in (
            "spam info bot",
            "spambot",
            "appeal has been denied",
            "restrictions have not been lifted",
            "your account is limited",
            "no restrictions",
            "free as a bird",
        )
    )


def _is_message_view(adb: AdbClient) -> bool:
    xml = adb.dump_ui_xml()
    return "org.thunderdog.challegram:id/msg_list" in xml and "org.thunderdog.challegram:id/msg_input" in xml


def _ocr(path: Path) -> str:
    proc = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", "eng", "--psm", "6"],
        capture_output=True,
        text=True,
        check=False,
    )
    text = "\n".join(part for part in [proc.stdout, proc.stderr] if part).strip()
    if proc.returncode != 0:
        raise RuntimeError(f"tesseract failed: {text}")
    return text


def _classify_spambot_text(text: str) -> dict:
    normalized = re.sub(r"\s+", " ", text.lower())
    denied_markers = [
        "appeal has been denied",
        "restrictions have not been lifted",
        "not been lifted",
        "has been denied",
        "account was blocked",
        "blocked for violations",
        "telegram terms of service",
        "user reports confirmed",
        "confirmed by our moderators",
    ]
    restricted_markers = [
        "account is limited",
        "your account is limited",
        "limited",
        "restricted",
        "restriction",
        "cannot send",
        "can't send",
        "can not send",
    ]
    normal_markers = [
        "no limits",
        "no restrictions",
        "free as a bird",
        "good news",
        "your account is free",
    ]

    if any(marker in normalized for marker in denied_markers):
        return {
            "is_banned": True,
            "has_restrictions": True,
            "restriction_note": "SpamBot: appeal denied; restrictions not lifted",
            "status_result": "banned",
        }
    if any(marker in normalized for marker in restricted_markers):
        return {
            "is_banned": False,
            "has_restrictions": True,
            "restriction_note": "SpamBot: restrictions detected",
            "status_result": "restricted",
        }
    if any(marker in normalized for marker in normal_markers):
        return {
            "is_banned": False,
            "has_restrictions": False,
            "restriction_note": "SpamBot: no restrictions detected",
            "status_result": "normal",
        }
    return {
        "is_banned": False,
        "has_restrictions": False,
        "restriction_note": "SpamBot result could not be classified automatically",
        "status_result": "unknown",
    }
