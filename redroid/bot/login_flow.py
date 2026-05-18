#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from .appium_client import AppiumClient, AppiumError
from .config import Config


START_BUTTONS = [
    "Start Messaging",
    "START MESSAGING",
    "Start",
    "Log In",
    "Continue",
    "开始使用",
    "开始",
    "继续",
    "登录",
]

NEXT_BUTTONS = [
    "Next",
    "NEXT",
    "Done",
    "OK",
    "Continue",
    "Allow",
    "Yes",
    "下一步",
    "完成",
    "确定",
    "继续",
    "允许",
    "是",
]

PASSWORD_HINTS = ["Password", "Two-Step Verification", "Cloud Password", "密码", "两步验证"]
CODE_HINTS = ["Code", "Telegram code", "验证码", "代码"]
LOGGED_IN_HINTS = ["Saved Messages", "New Message", "Settings", "Archived Chats", "已保存的消息", "设置"]
LOGGED_IN_RESOURCE_HINTS = [
    "org.thunderdog.challegram:id/chat",
    "org.thunderdog.challegram:id/menu_btn_search",
    "org.thunderdog.challegram:id/btn_float_compose",
    "org.thunderdog.challegram:id/btn_settings",
    "org.thunderdog.challegram:id/btn_username",
    "org.thunderdog.challegram:id/btn_phone",
]
ADD_ACCOUNT_BUTTONS = ["Add Account", "Add account", "添加账号", "添加帐户", "添加账户"]
ERROR_HINTS = ["Invalid", "Too many", "Flood", "error", "Sorry", "无效", "错误", "过于频繁", "请稍后"]
CONFIRM_HINTS = ["Is this phone number correct", "correct?", "确认", "是否正确", "phone number"]

COUNTRY_CODES = [
    "998", "996", "995", "994", "993", "992", "977", "976", "975", "974", "973", "972", "971", "970",
    "968", "967", "966", "965", "964", "963", "962", "961", "960", "886", "880", "856", "855", "852",
    "850", "692", "691", "690", "689", "688", "687", "686", "685", "683", "682", "681", "680", "679",
    "678", "677", "676", "675", "674", "673", "672", "670", "599", "598", "597", "596", "595", "594",
    "593", "592", "591", "590", "509", "508", "507", "506", "505", "504", "503", "502", "501", "500",
    "423", "421", "420", "389", "387", "386", "385", "383", "382", "381", "380", "379", "378", "377",
    "376", "375", "374", "373", "372", "371", "370", "359", "358", "357", "356", "355", "354", "353",
    "352", "351", "350", "299", "298", "297", "291", "290", "269", "268", "267", "266", "265", "264",
    "263", "262", "261", "260", "258", "257", "256", "255", "254", "253", "252", "251", "250", "249",
    "248", "246", "245", "244", "243", "242", "241", "240", "239", "238", "237", "236", "235", "234",
    "233", "232", "231", "230", "229", "228", "227", "226", "225", "224", "223", "222", "221", "220",
    "218", "216", "213", "212", "98", "95", "94", "93", "92", "91", "90", "86", "84", "82", "81",
    "66", "65", "64", "63", "62", "61", "60", "58", "57", "56", "55", "54", "53", "52", "51",
    "49", "48", "47", "46", "45", "44", "43", "41", "40", "39", "36", "34", "33", "32", "31", "30",
    "27", "20", "7", "1",
]


@dataclass
class ScreenState:
    kind: str
    message: str
    visible_texts: list[str]
    editable_fields: list[str]
    clickable_items: list[str]
    warnings: list[str] | None = None

    def bot_message(self) -> str:
        parts = [self.message]
        if self.warnings:
            parts.append("页面提示：\n" + "\n".join(f"- {x}" for x in self.warnings[:8]))
        if self.visible_texts:
            parts.append("页面文字：\n" + "\n".join(f"- {x}" for x in self.visible_texts[:12]))
        if self.editable_fields:
            parts.append("输入框：\n" + "\n".join(f"- {x}" for x in self.editable_fields[:8]))
        if self.clickable_items:
            parts.append("可点击项：\n" + "\n".join(f"- {x}" for x in self.clickable_items[:8]))
        return "\n\n".join(parts)


class TelegramXLoginFlow:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.client = AppiumClient(cfg)

    def close(self) -> None:
        self.client.close()

    def init_app(self) -> str:
        self.client.adb_connect()
        self.client.launch_app()
        self.client.create_session()
        time.sleep(2)
        self.dismiss_post_login_prompts()
        if self.is_phone_page():
            return "Telegram X 已经在手机号登录页。"
        if self.is_logged_in():
            return "Telegram X 已经处于登录后的界面。"
        clicked = self.client.click_by_text_candidates(START_BUTTONS, timeout=8)
        if clicked:
            time.sleep(2)
            return "已点击初始化/开始按钮。"
        self.client.press_keycode(4)
        time.sleep(1)
        if self.is_phone_page():
            return "已返回手机号登录页。"
        clicked = self.client.click_by_text_candidates(START_BUTTONS, timeout=3)
        if clicked:
            time.sleep(2)
            return "已点击初始化/开始按钮。"
        return "没有发现初始化按钮，可能已经进入登录页或已登录。"

    def dismiss_post_login_prompts(self) -> None:
        # Login may show contacts permission or one-time feature cards.
        self.client.click_by_text_candidates(["NEVER", "Never", "DENY", "Deny", "不允许", "拒绝"], timeout=1)
        texts = " ".join(self.client.page_texts())
        if "Folders are here" in texts or "START SETTING UP" in texts:
            self.client.press_keycode(4)
            time.sleep(1)

    def submit_phone(self, phone: str) -> str:
        self.prepare_phone_entry()
        time.sleep(1)
        phone_input = self.client.find_element_by_id("org.thunderdog.challegram:id/login_phone", timeout=10)
        code_input = self.client.find_element_by_id("org.thunderdog.challegram:id/login_code", timeout=2)
        if not phone_input:
            raise AppiumError("没有找到手机号输入框，请先点“初始化应用”或确认 Telegram X 在登录页。")
        country_code, national_number = self.split_phone(phone)
        if code_input and country_code:
            self.client.set_value(code_input, country_code)
        self.client.set_value(phone_input, national_number)
        time.sleep(0.5)
        if not self.client.click_by_text_candidates(NEXT_BUTTONS, timeout=4):
            self.client.press_keycode(66)
        time.sleep(3)
        self.handle_phone_confirmation()
        time.sleep(2)
        screen = self.describe_current_screen()
        if screen.kind == "password":
            return "password"
        if screen.kind == "code":
            return "code"
        if screen.kind == "logged_in":
            return "logged_in"
        if screen.kind == "error":
            raise AppiumError(screen.bot_message())
        return screen.kind

    def prepare_phone_entry(self) -> ScreenState:
        self.client.adb_connect()
        self.client.create_session()
        time.sleep(1)

        if self.is_phone_page():
            return self.describe_current_screen()

        if self.is_logged_in():
            self.open_add_account()
            if self.is_phone_page():
                return self.describe_current_screen()

        # On Telegram X code/password pages, Android BACK may be ignored while
        # the top-left toolbar button works. Try both before falling back to init.
        for _ in range(4):
            screen = self.describe_current_screen()
            if screen.kind == "phone" or self.is_phone_page():
                return self.describe_current_screen()
            self.client.tap(56, 104)
            time.sleep(1)
            if self.is_phone_page():
                return self.describe_current_screen()
            self.client.press_keycode(4)
            time.sleep(1)

        self.init_app()
        return self.describe_current_screen()

    def submit_code(self, code: str) -> str:
        edit = self.client.first_edit_text(timeout=10)
        if not edit:
            raise AppiumError("没有找到验证码输入框。")
        self.clear_text_field(edit)
        self.client.set_value(edit, code)
        time.sleep(0.5)
        self.client.press_keycode(66)
        time.sleep(5)
        if self.is_logged_in():
            return "logged_in"
        screen = self.describe_current_screen()
        if screen.kind == "password":
            return "password"
        if screen.kind == "error":
            raise AppiumError(screen.bot_message())
        return screen.kind if screen.kind != "unknown" else "waiting"

    def open_add_account(self) -> None:
        for _ in range(5):
            add_account = self.client.find_element_by_id("org.thunderdog.challegram:id/btn_addAccount", timeout=1)
            if add_account:
                self.client.click(add_account)
                time.sleep(2)
                return

            if self.is_settings_page():
                self.client.tap(56, 104)
                time.sleep(1)
                continue

            if self.is_drawer_open():
                self.client.tap(548, 288)
                time.sleep(1)
                continue

            self.client.tap(56, 104)
            time.sleep(1)

        if self.client.click_by_text_candidates(ADD_ACCOUNT_BUTTONS, timeout=2):
            time.sleep(2)
            return
        raise AppiumError("当前已登录，但没有找到 Add Account/添加账号入口。")

    def submit_password(self, password: str) -> str:
        edit = self.client.first_edit_text(timeout=10)
        if not edit:
            raise AppiumError("没有找到两步验证密码输入框。")
        self.clear_text_field(edit)
        self.client.set_value(edit, password)
        time.sleep(0.5)
        if not self.client.click_by_text_candidates(NEXT_BUTTONS, timeout=4):
            self.client.press_keycode(66)
        time.sleep(5)
        if self.is_logged_in():
            return "logged_in"
        screen = self.describe_current_screen()
        if screen.kind == "error":
            raise AppiumError(screen.bot_message())
        return screen.kind if screen.kind != "unknown" else "waiting"

    def clear_text_field(self, element_id: str) -> None:
        try:
            self.client.click(element_id)
            self.client.clear(element_id)
        except AppiumError:
            pass
        # WebDriver clear() is not reliable with Telegram X custom fields.
        # Move cursor to the end, then delete enough characters for code/password.
        try:
            self.client.press_keycode(123)
            for _ in range(64):
                self.client.press_keycode(67)
        except AppiumError:
            pass

    def handle_phone_confirmation(self) -> bool:
        texts = " ".join(self.client.page_texts())
        lowered = texts.lower()
        if not any(hint.lower() in lowered for hint in CONFIRM_HINTS):
            return False
        # Telegram X may show a confirmation dialog after the phone number.
        if self.client.click_by_text_candidates(["OK", "Ok", "Yes", "Confirm", "确定", "确认", "是"], timeout=3):
            return True
        return False

    def is_logged_in(self) -> bool:
        if self.is_phone_page():
            return False
        try:
            elements = self.client.parse_elements()
            texts = " ".join(item.text for item in elements if item.text)
            resource_ids = " ".join(item.resource_id for item in elements)
        except AppiumError:
            return False
        lowered = texts.lower()
        return (
            any(hint.lower() in lowered for hint in LOGGED_IN_HINTS)
            or any(hint in resource_ids for hint in LOGGED_IN_RESOURCE_HINTS)
        )

    def is_phone_page(self) -> bool:
        try:
            return self.client.find_element_by_id("org.thunderdog.challegram:id/login_phone", timeout=1) is not None
        except AppiumError:
            return False

    def is_settings_page(self) -> bool:
        try:
            return (
                self.client.find_element_by_id("org.thunderdog.challegram:id/btn_username", timeout=1) is not None
                and self.client.find_element_by_id("org.thunderdog.challegram:id/btn_phone", timeout=1) is not None
            )
        except AppiumError:
            return False

    def is_drawer_open(self) -> bool:
        try:
            return self.client.find_element_by_id("org.thunderdog.challegram:id/btn_settings", timeout=1) is not None
        except AppiumError:
            return False

    @staticmethod
    def split_phone(phone: str) -> tuple[str, str]:
        clean = re.sub(r"[^\d+]", "", phone.strip())
        if not clean.startswith("+"):
            return "", re.sub(r"\D+", "", clean)
        digits = re.sub(r"\D+", "", clean)
        for code in COUNTRY_CODES:
            if digits.startswith(code) and len(digits) > len(code):
                return code, digits[len(code):]
        return "", digits

    def read_profile(self) -> dict[str, Any]:
        profile: dict[str, Any] = {
            "telegram_user_id": "",
            "username": "",
            "first_name": "",
            "last_name": "",
            "raw_profile": "",
        }

        self.client.launch_app()
        time.sleep(1)
        self.dismiss_post_login_prompts()

        # Telegram X stores authenticated identity internally; its UI is heavily
        # custom-drawn, so exact text may not always be exposed through Appium.
        # We still navigate to Settings because resource IDs there are stable
        # and visible text is captured when this build exposes it.
        try:
            if not self.client.find_element_by_id("org.thunderdog.challegram:id/btn_settings", timeout=1):
                self.client.tap(56, 104)
                time.sleep(1)
            settings = self.client.find_element_by_id("org.thunderdog.challegram:id/btn_settings", timeout=2)
            if settings:
                self.client.click(settings)
                time.sleep(1)
        except AppiumError:
            pass

        elements = self.client.parse_elements()
        labels = [item.text for item in elements if item.text]
        raw_lines = []
        for item in elements[:120]:
            raw_lines.append(f"text={item.text!r} rid={item.resource_id!r} class={item.klass!r} bounds={item.bounds!r}")
        raw = "\n".join(raw_lines)
        profile["raw_profile"] = raw

        for label in labels:
            if label.startswith("@"):
                profile["username"] = label.lstrip("@").strip()
                break
            match = re.search(r"@([A-Za-z0-9_]{5,32})", label)
            if match:
                profile["username"] = match.group(1)
                break

        for label in labels:
            clean = label.strip()
            if clean and not clean.startswith("@") and not re.search(r"\d{4,}", clean):
                if clean not in {"Settings", "Saved Messages", "New Message", "Archived Chats"}:
                    profile["first_name"] = clean[:120]
                    break

        return profile

    def sync_current_account(self) -> dict[str, Any]:
        self.client.adb_connect()
        self.client.launch_app()
        self.client.create_session()
        time.sleep(2)
        self.dismiss_post_login_prompts()
        if not self.is_logged_in():
            screen = self.describe_current_screen()
            raise AppiumError("当前 Telegram X 未识别为登录状态。\n\n" + screen.bot_message())
        return self.read_profile()

    def describe_current_screen(self) -> ScreenState:
        elements = self.client.parse_elements()
        texts: list[str] = []
        editables: list[str] = []
        clickables: list[str] = []
        seen = set()
        for item in elements:
            label = (item.text or "").strip()
            if label and label not in seen:
                seen.add(label)
                texts.append(label)
            if "EditText" in item.klass:
                editables.append(f"{label or '(空)'} {item.resource_id}".strip())
            if item.clickable:
                clickables.append(f"{label or '(无文字按钮)'} {item.resource_id}".strip())

        joined = " ".join(texts).lower()
        resource_ids = " ".join(item.resource_id for item in elements)

        resource_ids = " ".join(item.resource_id for item in elements)

        warnings = [x for x in texts if any(hint.lower() in x.lower() for hint in ERROR_HINTS)]

        if self.is_phone_page():
            kind = "phone"
            message = "当前页面要求输入手机号。"
        elif self.client.find_element_by_id("org.thunderdog.challegram:id/btn_addAccount", timeout=1) is not None:
            kind = "drawer_accounts"
            message = "当前在侧边栏账号列表展开状态，可以点击 Add Account 添加账号。"
        elif self.is_settings_page():
            kind = "settings"
            message = "当前在 Telegram X 设置页。若要添加账号，应先返回侧边栏，再展开账号列表。"
        elif self.is_drawer_open():
            kind = "drawer"
            message = "当前在 Telegram X 侧边栏。若要添加账号，应先展开顶部账号列表。"
        elif any(hint.lower() in joined for hint in PASSWORD_HINTS):
            kind = "password"
            message = "当前页面要求输入两步验证密码。"
        elif any(hint.lower() in joined for hint in CODE_HINTS) or "controller_code" in resource_ids:
            kind = "code"
            message = "当前页面要求输入 Telegram 验证码。"
        elif self.is_logged_in():
            kind = "logged_in"
            message = "当前页面看起来已经登录成功。"
        elif warnings:
            kind = "error"
            message = "当前页面出现错误或限制提示。"
        elif any(hint.lower() in joined for hint in CONFIRM_HINTS):
            kind = "confirm"
            message = "当前页面要求确认手机号。"
        else:
            kind = "unknown"
            message = "当前页面无法明确归类，请根据页面文字判断下一步。"

        return ScreenState(kind, message, texts, editables, clickables, warnings)

    def login_with_code(self, phone: str, code: str, password: str | None = None) -> dict[str, Any]:
        self.submit_phone(phone)
        state = self.submit_code(code)
        if state == "password" and password:
            state = self.submit_password(password)
        if state != "logged_in":
            raise AppiumError(f"登录未完成，当前状态：{state}")
        return self.read_profile()
