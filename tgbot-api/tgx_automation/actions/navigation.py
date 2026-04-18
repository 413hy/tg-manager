from __future__ import annotations

from tgx_automation.adb_client import AdbClient


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
