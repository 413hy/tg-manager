from __future__ import annotations

from tgx_automation.adb_client import AdbClient
from tgx_automation.ui_xml import (
    find_node_by_resource,
    find_node_by_text,
    find_top_right_close,
)


def _tap_node(adb: AdbClient, node) -> bool:
    if not node:
        return False
    center = node.center
    if not center:
        return False
    adb.tap(*center)
    return True


def handle_common_interstitials(adb: AdbClient) -> list[str]:
    actions: list[str] = []
    xml = adb.dump_ui_xml()

    # Prefer explicit skip/never/not-now buttons
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

    close = find_top_right_close(xml)
    if _tap_node(adb, close):
        actions.append("clicked top-right close")
        return actions

    if "more_btn_logout" in xml.lower():
        adb.keyevent(4)
        actions.append("dismissed logout menu")

    return actions
