from __future__ import annotations

import subprocess
import threading
import time
import shlex
import base64
from pathlib import Path
from typing import Sequence

from tgx_automation.config import settings


class AdbClient:
    def __init__(self, serial: str) -> None:
        self.serial = serial
        self._lock = threading.Lock()

    def _run(self, args: Sequence[str]) -> str:
        cmd = ["adb", "-s", self.serial, *args]
        with self._lock:
            proc = self._run_raw(cmd)
            if proc.returncode != 0 and self._looks_like_offline_adb(proc):
                self._repair_adb_transport()
                proc = self._run_raw(cmd)
        if proc.returncode != 0:
            raise RuntimeError(f"ADB failed: {' '.join(cmd)}\n{proc.stderr}")
        return proc.stdout.strip()

    @staticmethod
    def _run_raw(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(cmd, capture_output=True, text=True, check=False)

    @staticmethod
    def _looks_like_offline_adb(proc: subprocess.CompletedProcess[str]) -> bool:
        text = f"{proc.stdout}\n{proc.stderr}".lower()
        return any(
            marker in text
            for marker in (
                "device offline",
                "device '",
                "not found",
                "device still connecting",
                "no devices/emulators found",
                "cannot connect to daemon",
                "failed to start daemon",
            )
        )

    def _repair_adb_transport(self) -> None:
        if ":" not in self.serial:
            return
        host, port = self.serial.rsplit(":", 1)
        if host not in {"127.0.0.1", "localhost"} or not port.isdigit():
            return

        container = settings.redroid_name
        repair_commands = [
            ["docker", "exec", container, "am", "force-stop", "com.hagaseca.thost9"],
            ["docker", "exec", container, "setprop", "service.adb.tcp.port", "5555"],
            ["docker", "exec", container, "setprop", "ctl.restart", "adbd"],
            ["adb", "kill-server"],
        ]
        for command in repair_commands:
            self._run_raw(command)
        time.sleep(1.2)
        self._run_raw(["adb", "start-server"])
        self._run_raw(["adb", "connect", self.serial])

    def shell(self, command: str) -> str:
        return self._run(["shell", command])

    def tap(self, x: int, y: int) -> None:
        self.shell(f"input tap {x} {y}")

    def keyevent(self, keycode: int) -> None:
        self.shell(f"input keyevent {keycode}")

    def input_text(self, value: str) -> None:
        if _is_plain_adb_text(value):
            self._input_plain_text(value)
        else:
            self._input_unicode_text(value)

    def _input_plain_text(self, value: str) -> None:
        safe = value.replace(" ", "%s")
        self.shell(f"input text {shlex.quote(safe)}")

    def _input_unicode_text(self, value: str) -> None:
        current_ime = self.shell("settings get secure default_input_method")
        encoded = _modified_utf7_imap_encode(value)
        try:
            self.shell("ime set io.appium.settings/.UnicodeIME")
            time.sleep(0.2)
            self.shell(f"input text {shlex.quote(encoded)}")
        finally:
            if current_ime and current_ime != "null":
                self.shell(f"ime set {shlex.quote(current_ime)}")

    def push(self, local_path: Path, remote_path: str) -> str:
        return self._run(["push", str(local_path), remote_path])

    def scan_media(self, remote_path: str) -> str:
        return self.shell(
            "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE "
            f"-d {shlex.quote('file://' + remote_path)}"
        )

    def start_activity(self, activity: str) -> str:
        return self._run(["shell", "am", "start", "-n", activity])

    def force_stop(self, package: str = "org.thunderdog.challegram") -> str:
        return self._run(["shell", "am", "force-stop", package])

    def dump_ui_xml(self) -> str:
        last_error: Exception | None = None
        for _ in range(3):
            try:
                self.shell("uiautomator dump /sdcard/window_dump.xml")
                return self.shell("cat /sdcard/window_dump.xml")
            except RuntimeError as exc:
                last_error = exc
                time.sleep(0.4)
        raise RuntimeError(f"failed to dump UI XML after retries: {last_error}")

    def screenshot(self, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        last_error = ""
        for _ in range(5):
            proc = subprocess.run(
                ["adb", "-s", self.serial, "exec-out", "screencap", "-p"],
                capture_output=True,
                check=False,
            )
            png = _extract_complete_png(proc.stdout)
            if proc.returncode == 0 and png:
                out_path.write_bytes(png)
                return
            last_error = proc.stderr.decode("utf-8", errors="replace") if isinstance(proc.stderr, bytes) else str(proc.stderr)
            time.sleep(0.4)

        remote_path = "/sdcard/tgx_screenshot.png"
        for _ in range(3):
            proc = subprocess.run(
                ["adb", "-s", self.serial, "shell", "screencap", "-p", remote_path],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                last_error = proc.stderr
                time.sleep(0.4)
                continue
            pull = subprocess.run(
                ["adb", "-s", self.serial, "pull", remote_path, str(out_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if pull.returncode == 0:
                data = out_path.read_bytes()
                png = _extract_complete_png(data)
                if png:
                    out_path.write_bytes(png)
                    return
            last_error = pull.stderr
            time.sleep(0.4)
        raise RuntimeError(f"failed screenshot: invalid or truncated PNG {last_error}".strip())


def _is_plain_adb_text(value: str) -> bool:
    return all(0x20 <= ord(ch) <= 0x7E for ch in value)


def _extract_complete_png(data: bytes) -> bytes | None:
    start = data.find(b"\x89PNG\r\n\x1a\n")
    if start < 0:
        return None
    end_marker = b"IEND\xaeB`\x82"
    end = data.find(end_marker, start)
    if end < 0:
        return None
    return data[start : end + len(end_marker)]


def _modified_utf7_imap_encode(value: str) -> str:
    result: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        raw = "".join(buf).encode("utf-16-be")
        token = base64.b64encode(raw).decode("ascii").rstrip("=").replace("/", ",")
        result.append(f"&{token}-")
        buf.clear()

    for ch in value:
        code = ord(ch)
        if ch == "&":
            flush()
            result.append("&-")
        elif 0x20 <= code <= 0x7E:
            flush()
            result.append(ch)
        else:
            buf.append(ch)
    flush()
    return "".join(result)
