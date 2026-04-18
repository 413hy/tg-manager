from __future__ import annotations

from tgx_automation.adb_client import AdbClient


def handle_common_interstitials(adb: AdbClient) -> list[str]:
    actions: list[str] = []
    xml = adb.dump_ui_xml().lower()

    if "start setting up" in xml and "btn_done" in xml:
        adb.tap(360, 1128)
        actions.append("clicked START SETTING UP")

    if "never" in xml:
        adb.tap(120, 1100)
        actions.append("clicked NEVER")

    if "not now" in xml or "skip" in xml or "later" in xml:
        adb.tap(360, 1100)
        actions.append("clicked not-now/skip")

    if "more_btn_logout" in xml:
        adb.keyevent(4)
        actions.append("dismissed logout menu")

    return actions
