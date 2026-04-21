from __future__ import annotations

import re
import time
from pathlib import PurePosixPath

from tgx_automation.adb_client import AdbClient
from tgx_automation.ui_xml import find_node_by_resource, parse_nodes


USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def open_settings(adb: AdbClient) -> str:
    adb.open_deeplink("tg://settings")
    time.sleep(1.0)
    if _settings_visible(adb):
        return "open settings"

    # Android's "Open link as..." sheet is not exposed through uiautomator on
    # this redroid build, so accept the bottom-right OPEN button by coordinate.
    adb.tap(650, 1132)
    time.sleep(1.0)
    if _settings_visible(adb):
        return "open settings"

    adb.force_stop()
    time.sleep(0.4)
    adb.open_deeplink("tg://settings")
    time.sleep(1.0)
    if not _settings_visible(adb):
        adb.tap(650, 1132)
        time.sleep(1.0)
    return "open settings"


def read_visible_profile_fields(adb: AdbClient) -> dict[str, str]:
    open_settings(adb)
    xml = adb.dump_ui_xml()
    if "btn_username" not in xml:
        raise RuntimeError("Telegram X settings page was not reached")
    fields = _read_profile_fields_from_xml(xml)

    username = _read_username_from_editor(adb, xml)
    if username:
        fields["username"] = username

    return fields


def _settings_visible(adb: AdbClient) -> bool:
    return "btn_username" in adb.dump_ui_xml()


def tap_resource_with_scroll(
    adb: AdbClient,
    resource: str,
    *,
    max_scrolls: int = 3,
    scroll_down: bool = True,
) -> list[str]:
    steps: list[str] = []
    for attempt in range(max_scrolls + 1):
        xml = adb.dump_ui_xml()
        node = find_node_by_resource(xml, [resource])
        if node and node.center:
            adb.tap(*node.center)
            steps.append(f"tap {resource}")
            time.sleep(0.9)
            return steps
        if attempt < max_scrolls:
            if scroll_down:
                adb.shell("input swipe 360 1040 360 430 500")
            else:
                adb.shell("input swipe 360 430 360 1040 500")
            steps.append("scroll settings")
            time.sleep(0.7)
    raise RuntimeError(f"resource not found: {resource}")


def open_devices_page(adb: AdbClient) -> list[str]:
    steps = [open_settings(adb)]
    steps.extend(tap_resource_with_scroll(adb, "btn_devices", max_scrolls=2))
    return steps


def open_privacy_page(adb: AdbClient) -> list[str]:
    steps = [open_settings(adb)]
    steps.extend(tap_resource_with_scroll(adb, "btn_privacySettings", max_scrolls=3))
    return steps


def open_active_sessions_page(adb: AdbClient) -> list[str]:
    steps = open_privacy_page(adb)
    steps.extend(tap_resource_with_scroll(adb, "btn_sessions", max_scrolls=1))
    return steps


def open_two_fa_page(adb: AdbClient) -> list[str]:
    steps = open_privacy_page(adb)
    steps.extend(tap_resource_with_scroll(adb, "btn_2fa", max_scrolls=1))
    return steps


def open_login_email_page(adb: AdbClient) -> list[str]:
    steps = open_privacy_page(adb)
    steps.extend(tap_resource_with_scroll(adb, "btn_loginEmail", max_scrolls=1))
    return steps


def _read_profile_fields_from_xml(xml: str) -> dict[str, str]:
    values: list[str] = []
    for node in parse_nodes(xml):
        value = (node.text or node.content_desc).strip()
        if value and value not in values:
            values.append(value)

    fields: dict[str, str] = {}
    for value in values:
        username = _extract_username(value)
        if username:
            fields["username"] = username
        elif value.startswith("+") and any(ch.isdigit() for ch in value):
            fields["phone"] = value

    # Telegram X often renders profile text as custom-drawn views. When values are
    # not exposed through accessibility XML, leave fields empty instead of guessing.
    text_values = [
        value
        for value in values
        if value
        and not value.startswith("@")
        and not value.startswith("+")
        and value.lower() not in {"settings", "edit", "phone", "username"}
    ]
    if text_values:
        name_parts = text_values[0].split(maxsplit=1)
        fields["first_name"] = name_parts[0]
        if len(name_parts) > 1:
            fields["last_name"] = name_parts[1]
    return fields


def _extract_username(value: str) -> str | None:
    text = value.strip()
    if text.startswith("@"):
        text = text[1:]
    elif "t.me/" in text:
        text = text.rsplit("t.me/", maxsplit=1)[-1].split()[0].strip("/")
    else:
        return None
    return text if USERNAME_RE.match(text) else None


def _read_username_from_editor(adb: AdbClient, settings_xml: str) -> str | None:
    username_row = find_node_by_resource(settings_xml, ["btn_username"])
    center = username_row.center if username_row else None
    if center:
        adb.tap(*center)
    else:
        adb.tap(360, 616)
    time.sleep(0.8)

    sheet_xml = adb.dump_ui_xml()
    if "controller_editUsername" not in sheet_xml:
        adb.tap(214, 917)
        time.sleep(0.8)

    editor_xml = adb.dump_ui_xml()
    username = _find_username_input(editor_xml)
    for _ in range(2):
        adb.keyevent(4)
        time.sleep(0.2)
    return username


def _find_username_input(xml: str) -> str | None:
    for node in parse_nodes(xml):
        value = node.text.strip()
        if node.resource_id.endswith(":id/input") and USERNAME_RE.match(value):
            return value

    for node in parse_nodes(xml):
        for value in (node.text.strip(), node.content_desc.strip()):
            username = _extract_username(value)
            if username:
                return username
    return None


def open_username_editor(adb: AdbClient) -> list[str]:
    steps = []
    adb.tap(360, 616)
    steps.append("tap btn_username")
    # fallback overlay button if present in this build
    adb.tap(632, 512)
    steps.append("tap username overlay/fab")
    return steps


def change_username_for_current_account(adb: AdbClient, username: str) -> list[str]:
    steps = [open_settings(adb)]
    steps.extend(open_username_editor(adb))
    steps.extend(change_username(adb, username))
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
    time.sleep(1.5)
    return steps


def open_name_editor(adb: AdbClient) -> list[str]:
    steps = [open_settings(adb)]
    xml = adb.dump_ui_xml()
    if "btn_birthdate" in xml and "btn_bio" in xml:
        return steps

    # In this Telegram X build the visible pencil on the profile header opens
    # avatar actions, and the overflow menu only exposes logout. Do not continue
    # with blind coordinates, otherwise the database may be updated after a
    # failed UI action.
    raise RuntimeError(
        "Telegram X did not expose a profile name editor on this page; "
        "name was not changed and database was not updated"
    )


def change_name(adb: AdbClient, first_name: str, last_name: str) -> list[str]:
    steps = open_name_editor(adb)
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
    time.sleep(1.5)
    return steps


def change_avatar_from_gallery(adb: AdbClient, expected_remote_path: str | None = None) -> list[str]:
    steps = []
    steps.append(open_settings(adb))

    adb.tap(450, 300)
    steps.append("tap profile photo")
    time.sleep(0.8)

    adb.tap(260, 1024)
    steps.append("tap set profile photo")
    time.sleep(0.8)

    adb.tap(360, 714)
    steps.append("allow media if prompted")
    time.sleep(0.8)

    if expected_remote_path:
        latest = latest_image_path(adb)
        steps.append(f"latest media={latest or '-'}")
        if not _same_android_path(latest, expected_remote_path):
            raise RuntimeError(
                "avatar target is not the newest media item; refusing to select the first gallery tile "
                f"(expected {expected_remote_path}, latest {latest or '-'})"
            )

    adb.tap(360, 770)
    steps.append("pick first media")
    time.sleep(0.8)

    adb.tap(664, 1128)
    steps.append("confirm avatar")
    time.sleep(1.2)

    xml = adb.dump_ui_xml()
    if "Profile photo" in xml or "Set Profile Photo" in xml:
        adb.tap(665, 1128)
        steps.append("confirm avatar crop")
        time.sleep(2.5)

    xml = adb.dump_ui_xml()
    if "btn_username" not in xml:
        raise RuntimeError("avatar was not confirmed; Telegram X did not return to settings")
    if expected_remote_path:
        steps.append("verified target by MediaStore latest item before selection")
    return steps


def prepare_avatar_media(adb: AdbClient, local_path, extension: str = ".jpg", stem: str = "tgx_custom_avatar") -> tuple[list[str], str]:
    remote_path = f"/sdcard/Pictures/{stem}{extension}"
    adb.push(local_path, remote_path)
    adb.scan_media(remote_path)
    time.sleep(0.8)
    return [f"push avatar media {remote_path}", "scan avatar media"], remote_path


def latest_image_path(adb: AdbClient) -> str | None:
    output = adb.shell(
        "content query --uri content://media/external/images/media "
        "--projection _id:_data:date_added --sort 'date_added DESC'"
    )
    for line in output.splitlines():
        match = re.search(r"_data=([^,]+)", line)
        if match:
            return match.group(1).strip()
    return None


def _same_android_path(actual: str | None, expected: str) -> bool:
    if not actual:
        return False
    actual_path = PurePosixPath(actual)
    expected_path = PurePosixPath(expected)
    if str(actual_path) == str(expected_path):
        return True
    if str(expected_path).startswith("/sdcard/"):
        normalized = "/storage/emulated/0/" + str(expected_path)[len("/sdcard/") :]
        return str(actual_path) == normalized
    return False
