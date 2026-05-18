#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from .config import Config


class AppiumError(RuntimeError):
    pass


@dataclass
class ElementInfo:
    text: str
    klass: str
    resource_id: str
    bounds: str
    clickable: bool


class AppiumClient:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.session_id: str | None = None

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> Any:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{self.cfg.appium_url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise AppiumError(f"Appium request failed: {exc}") from exc
        parsed = json.loads(body) if body else {}
        if "value" in parsed:
            value = parsed["value"]
            if isinstance(value, dict) and value.get("error"):
                raise AppiumError(value.get("message") or str(value))
            return value
        return parsed

    def status(self) -> dict[str, Any]:
        return self.request("GET", "/status", timeout=10)

    def create_session(self) -> str:
        if self.session_id:
            return self.session_id
        payload = {
            "capabilities": {
                "alwaysMatch": {
                    "platformName": "Android",
                    "appium:automationName": "UiAutomator2",
                    "appium:deviceName": "redroid",
                    "appium:udid": self.cfg.adb_serial,
                    "appium:appPackage": self.cfg.app_package,
                    "appium:appActivity": self.cfg.app_activity,
                    "appium:noReset": True,
                    "appium:autoGrantPermissions": True,
                    "appium:newCommandTimeout": 300,
                }
            }
        }
        value = self.request("POST", "/session", payload, timeout=120)
        self.session_id = value["sessionId"]
        return self.session_id

    def close(self) -> None:
        if self.session_id:
            try:
                self.request("DELETE", f"/session/{self.session_id}", timeout=10)
            finally:
                self.session_id = None

    def _session_path(self, suffix: str) -> str:
        sid = self.create_session()
        return f"/session/{sid}{suffix}"

    def source(self) -> str:
        return self.request("GET", self._session_path("/source"), timeout=30)

    def page_texts(self) -> list[str]:
        xml = self.source()
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return []
        values: list[str] = []
        for node in root.iter():
            for attr in ("text", "content-desc", "resource-id"):
                value = node.attrib.get(attr)
                if value:
                    values.append(value)
        return values

    def find_element(self, using: str, value: str, timeout: int = 5) -> str | None:
        deadline = time.time() + timeout
        payload = {"using": using, "value": value}
        while time.time() <= deadline:
            try:
                found = self.request("POST", self._session_path("/element"), payload, timeout=10)
                element_id = found.get("element-6066-11e4-a52e-4f735466cecf") or found.get("ELEMENT")
                if element_id:
                    return element_id
            except AppiumError:
                pass
            time.sleep(0.5)
        return None

    def find_element_by_id(self, resource_id: str, timeout: int = 5) -> str | None:
        return self.find_element("id", resource_id, timeout=timeout)

    def click(self, element_id: str) -> None:
        self.request("POST", self._session_path(f"/element/{element_id}/click"), {}, timeout=10)

    def clear(self, element_id: str) -> None:
        self.request("POST", self._session_path(f"/element/{element_id}/clear"), {}, timeout=10)

    def set_value(self, element_id: str, text: str) -> None:
        try:
            self.clear(element_id)
        except AppiumError:
            pass
        self.request(
            "POST",
            self._session_path(f"/element/{element_id}/value"),
            {"text": text, "value": list(text)},
            timeout=10,
        )

    def tap(self, x: int, y: int) -> None:
        self.request(
            "POST",
            self._session_path("/actions"),
            {
                "actions": [
                    {
                        "type": "pointer",
                        "id": "finger1",
                        "parameters": {"pointerType": "touch"},
                        "actions": [
                            {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                            {"type": "pointerDown", "button": 0},
                            {"type": "pause", "duration": 80},
                            {"type": "pointerUp", "button": 0},
                        ],
                    }
                ]
            },
            timeout=10,
        )

    def press_keycode(self, keycode: int) -> None:
        self.request("POST", self._session_path("/appium/device/press_keycode"), {"keycode": keycode}, timeout=10)

    def click_by_text_candidates(self, candidates: list[str], timeout: int = 5) -> bool:
        xpath_parts = []
        for item in candidates:
            escaped = item.replace("'", "\\'")
            xpath_parts.append(f"@text='{escaped}'")
            xpath_parts.append(f"@content-desc='{escaped}'")
        xpath = "//*[" + " or ".join(xpath_parts) + "]"
        element = self.find_element("xpath", xpath, timeout=timeout)
        if element:
            self.click(element)
            return True
        return False

    def first_edit_text(self, timeout: int = 5) -> str | None:
        return self.find_element("class name", "android.widget.EditText", timeout=timeout)

    def screenshot_base64(self) -> str:
        return self.request("GET", self._session_path("/screenshot"), timeout=30)

    def save_screenshot(self, path: str) -> None:
        data = base64.b64decode(self.screenshot_base64())
        with open(path, "wb") as fh:
            fh.write(data)

    def adb(self, args: list[str], timeout: int = 30) -> str:
        cmd = ["adb", "-s", self.cfg.adb_serial] + args
        result = subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=timeout)
        if result.returncode != 0:
            raise AppiumError((result.stderr or result.stdout).strip())
        return result.stdout.strip()

    def adb_connect(self) -> None:
        subprocess.run(["adb", "start-server"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["adb", "connect", self.cfg.adb_serial], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def launch_app(self) -> None:
        self.adb(["shell", "am", "start", "-n", f"{self.cfg.app_package}/{self.cfg.app_activity}"], timeout=20)

    def current_activity(self) -> str:
        return self.adb(["shell", "dumpsys", "window", "windows"], timeout=20)

    def parse_elements(self) -> list[ElementInfo]:
        xml = self.source()
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return []
        items: list[ElementInfo] = []
        for node in root.iter():
            text = node.attrib.get("text", "")
            desc = node.attrib.get("content-desc", "")
            label = text or desc
            klass = node.attrib.get("class", "")
            rid = node.attrib.get("resource-id", "")
            bounds = node.attrib.get("bounds", "")
            clickable = node.attrib.get("clickable") == "true"
            if label or "EditText" in klass or clickable:
                items.append(ElementInfo(label, klass, rid, bounds, clickable))
        return items

    @staticmethod
    def digits(text: str) -> str:
        return re.sub(r"\D+", "", text)
