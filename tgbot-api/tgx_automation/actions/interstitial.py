from __future__ import annotations

from tgx_automation.adb_client import AdbClient
from tgx_automation.ui_xml import (
    find_node_by_resource,
    find_node_by_text,
    find_top_right_close,
)


POPUP_HINTS = [
    "start setting up",
    "folders are here",
    "never",
    "skip",
    "not now",
    "later",
    "more_btn_logout",
]


def _tap_node(adb: AdbClient, node) -> bool:
    if not node:
        return False
    center = node.center
    if not center:
        return False
    adb.tap(*center)
    return True


def _try_back_first(adb: AdbClient, xml: str) -> bool:
    x = xml.lower()
    if any(h in x for h in POPUP_HINTS):
        adb.keyevent(4)
        return True
    return False


def handle_common_interstitials(adb: AdbClient) -> list[str]:
    actions: list[str] = []
    xml = adb.dump_ui_xml()

    old_android_dialog = "older version of android" in xml.lower()
    if old_android_dialog:
        ok_node = find_node_by_text(xml, ["ok"])
        if _tap_node(adb, ok_node):
            actions.append("clicked Android compatibility dialog OK")
            return actions

    # Most stable strategy in practice: back key first for transient overlays.
    if _try_back_first(adb, xml):
        actions.append("pressed BACK to dismiss popup/interstitial")
        return actions

    # If back didn't apply, fallback to explicit buttons.
    skip_node = find_node_by_text(xml, ["never", "skip", "not now", "later"])
    if _tap_node(adb, skip_node):
        actions.append(f"clicked interstitial text button: {skip_node.text}")
        return actions

    start_setup = find_node_by_text(xml, ["start setting up", "start"])
    if _tap_node(adb, start_setup):
        actions.append(f"clicked CTA: {start_setup.text}")
        return actions

    by_done = find_node_by_resource(xml, ["btn_done"])
    if _tap_node(adb, by_done):
        actions.append("clicked btn_done")
        return actions

    if any(h in xml.lower() for h in POPUP_HINTS):
        close = find_top_right_close(xml)
        if _tap_node(adb, close):
            actions.append("clicked top-right close")
            return actions

    return actions
