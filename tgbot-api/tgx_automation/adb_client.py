from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence


class AdbClient:
    def __init__(self, serial: str) -> None:
        self.serial = serial

    def _run(self, args: Sequence[str]) -> str:
        cmd = ["adb", "-s", self.serial, *args]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"ADB failed: {' '.join(cmd)}\n{proc.stderr}")
        return proc.stdout.strip()

    def shell(self, command: str) -> str:
        return self._run(["shell", command])

    def tap(self, x: int, y: int) -> None:
        self.shell(f"input tap {x} {y}")

    def keyevent(self, keycode: int) -> None:
        self.shell(f"input keyevent {keycode}")

    def input_text(self, value: str) -> None:
        safe = value.replace(" ", "%s")
        self.shell(f"input text {safe}")

    def start_activity(self, activity: str) -> str:
        return self._run(["shell", "am", "start", "-n", activity])

    def open_deeplink(self, url: str, package: str = "org.thunderdog.challegram") -> str:
        return self._run(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url, package])

    def force_stop(self, package: str = "org.thunderdog.challegram") -> str:
        return self._run(["shell", "am", "force-stop", package])

    def dump_ui_xml(self) -> str:
        self.shell("uiautomator dump /sdcard/window_dump.xml")
        return self.shell("cat /sdcard/window_dump.xml")

    def screenshot(self, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["adb", "-s", self.serial, "exec-out", "screencap", "-p"],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError("failed screenshot")
        out_path.write_bytes(proc.stdout)
