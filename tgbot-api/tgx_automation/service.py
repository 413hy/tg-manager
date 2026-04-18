from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tgx_automation.actions.interstitial import handle_common_interstitials
from tgx_automation.actions.navigation import recover_home
from tgx_automation.adb_client import AdbClient
from tgx_automation.pages.detector import detect_page
from tgx_automation.pages.models import PageSnapshot, PageType


@dataclass
class RouterResult:
    page: PageType
    actions: list[str]
    note: str


class AutomationService:
    def __init__(self, adb: AdbClient) -> None:
        self.adb = adb

    def snapshot(self) -> PageSnapshot:
        xml = self.adb.dump_ui_xml()
        return detect_page(xml)

    def step_router(self) -> RouterResult:
        snap = self.snapshot()
        actions: list[str] = []

        if snap.page == PageType.INTERSTITIAL:
            actions.extend(handle_common_interstitials(self.adb))
            return RouterResult(page=snap.page, actions=actions, note="interstitial handled")

        if snap.page == PageType.UNKNOWN:
            actions.extend(recover_home(self.adb))
            return RouterResult(page=snap.page, actions=actions, note="unknown -> recovered home")

        return RouterResult(page=snap.page, actions=actions, note="no-op")

    def debug_info(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {"page": snap.page, "hints": snap.hints, "excerpt": snap.xml_excerpt}
