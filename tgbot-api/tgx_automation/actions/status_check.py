from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from tgx_automation.actions.interstitial import handle_common_interstitials
from tgx_automation.actions.navigation import recover_home
from tgx_automation.adb_client import AdbClient
from tgx_automation.ui_xml import find_node_by_resource, parse_nodes


class SpamBotOpenError(RuntimeError):
    def __init__(self, message: str, steps: list[str]) -> None:
        super().__init__(message)
        self.steps = steps


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
    steps.append("ocr current SpamBot response")
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
    _wait_for_search(adb)
    _clear_search(adb)
    adb.input_text("SpamBot")
    steps.append("search SpamBot")
    time.sleep(1.5)
    centers = _search_result_centers(adb)
    for index, center in enumerate(centers, start=1):
        adb.tap(*center)
        steps.append(f"open search result candidate {index}")
        time.sleep(4)
        steps.append(_ocr_excerpt(adb, work_dir / f"spambot-search-candidate-{index}.png", f"search candidate {index}"))
        if _is_spambot_view(adb, work_dir, f"search-{index}"):
            return steps
        adb.keyevent(4)
        steps.append(f"search candidate {index} is not SpamBot")
        time.sleep(0.8)

    steps.extend(_try_visible_chat_candidates(adb, work_dir))
    if not _is_spambot_view(adb, work_dir, "fallback"):
        raise SpamBotOpenError("failed to open SpamBot chat", steps)
    return steps


def _send_start(adb: AdbClient) -> list[str]:
    xml = adb.dump_ui_xml()
    input_node = find_node_by_resource(xml, ["msg_input"])
    if input_node and input_node.center:
        adb.tap(*input_node.center)
    else:
        adb.tap(260, 1135)
    time.sleep(0.2)
    _clear_message_input(adb)
    if _message_input_text(adb).strip():
        raise RuntimeError("failed to clear SpamBot message input before /start")
    adb.input_text("/start")
    if _message_input_text(adb).strip() != "/start":
        raise RuntimeError("failed to prepare exact /start command for SpamBot")
    time.sleep(0.2)
    _tap_send(adb)
    if _input_has_start(adb):
        raise RuntimeError("failed to send exact /start command to SpamBot")
    time.sleep(4)
    return ["clear input and send exact /start to SpamBot"]


def _clear_message_input(adb: AdbClient) -> None:
    if not _message_input_text(adb).strip():
        return
    adb.keyevent(123)
    adb.shell("i=0; while [ $i -lt 80 ]; do input keyevent 67; i=$((i+1)); done")


def _tap_send(adb: AdbClient) -> None:
    send_node = find_node_by_resource(adb.dump_ui_xml(), ["msg_send"])
    if send_node and send_node.center:
        adb.tap(*send_node.center)
        time.sleep(0.5)
    if _input_has_start(adb):
        adb.tap(670, 1135)


def _input_has_start(adb: AdbClient) -> bool:
    return "/start" in _message_input_text(adb)


def _message_input_text(adb: AdbClient) -> str:
    input_node = find_node_by_resource(adb.dump_ui_xml(), ["msg_input"])
    return input_node.text if input_node else ""


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


def _wait_for_search(adb: AdbClient) -> None:
    for _ in range(4):
        xml = adb.dump_ui_xml()
        if "menu_btn_clear" in xml or 'text="Search"' in xml:
            return
        time.sleep(0.4)
    adb.tap(671, 104)
    time.sleep(0.8)


def _clear_search(adb: AdbClient) -> None:
    for _ in range(2):
        xml = adb.dump_ui_xml()
        clear_button = find_node_by_resource(xml, ["menu_btn_clear"])
        search_field = next((node for node in parse_nodes(xml) if node.text and node.center and node.center[1] < 180), None)
        if clear_button and clear_button.center and search_field and search_field.text not in {"", "Search"}:
            adb.tap(*clear_button.center)
            time.sleep(0.3)
            continue
        return


def _search_result_centers(adb: AdbClient) -> list[tuple[int, int]]:
    xml = adb.dump_ui_xml()
    centers: list[tuple[int, int]] = []
    for node in parse_nodes(xml):
        if not node.center:
            continue
        if (
            node.resource_id.endswith(":id/search_chat_local")
            or node.resource_id.endswith(":id/search_chat_global")
            or node.resource_id.endswith(":id/chat")
        ):
            centers.append(node.center)
    if centers:
        return sorted(set(centers), key=lambda center: center[1])[:6]

    for node in parse_nodes(xml):
        if node.clickable and node.center:
            x, y = node.center
            if 180 <= y <= 460 and x >= 60:
                centers.append((x, y))
    return sorted(set(centers), key=lambda center: center[1])[:6]


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
    screenshot = work_dir / f"spambot-open-{label}.png"
    adb.screenshot(screenshot)
    text = _ocr(screenshot).lower()
    is_spambot = any(
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
    if not is_spambot:
        return False
    if _is_message_view(adb):
        return True
    adb.tap(360, 1050)
    time.sleep(2)
    return _is_message_view(adb)


def _ocr_excerpt(adb: AdbClient, path: Path, label: str) -> str:
    adb.screenshot(path)
    text = re.sub(r"\s+", " ", _ocr(path)).strip()
    return f"{label} OCR: {text[:160]}"


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
    normalized = _normalize_spambot_text(text)

    if _contains_all(
        normalized,
        (
            "your account was blocked for violations of the telegram terms of service",
            "based on user reports confirmed by our moderators",
        ),
    ):
        return {
            "is_banned": True,
            "has_restrictions": True,
            "restriction_note": "SpamBot: account blocked for Terms of Service violations",
            "status_result": "banned",
        }
    if _contains_all(
        normalized,
        (
            "unfortunately some phone numbers may trigger a harsh response from our anti spam systems",
            "submit a complaint to our moderators",
            "telegram premium",
            "less strict limits",
        ),
    ):
        return {
            "is_banned": False,
            "has_restrictions": True,
            "restriction_note": "SpamBot: phone number triggered anti-spam limits",
            "status_result": "restricted",
        }
    if _contains_all(
        normalized,
        (
            "good news no limits are currently applied to your account",
            "youre free as a",
        ),
    ) and ("bird" in normalized or "ird" in normalized):
        return {
            "is_banned": False,
            "has_restrictions": False,
            "restriction_note": "SpamBot: no limits are currently applied",
            "status_result": "normal",
        }
    return {
        "is_banned": False,
        "has_restrictions": False,
        "restriction_note": "SpamBot query failed: unrecognized response",
        "status_result": "unknown",
    }


def _normalize_spambot_text(text: str) -> str:
    normalized = text.lower().replace("’", "").replace("'", "")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _contains_all(text: str, fragments: tuple[str, ...]) -> bool:
    return all(fragment in text for fragment in fragments)
