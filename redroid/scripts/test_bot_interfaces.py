#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, "/root/redroid")

os.environ["TG_BOT_TOKEN"] = "test-token"
os.environ["TG_BOT_ALLOWED_USER_ID"] = "111111111"
os.environ["TG_BOT_DB"] = tempfile.mktemp(prefix="tg-redroid-test-", suffix=".sqlite3")

from bot import bot as bot_module  # noqa: E402


ALLOWED = 111111111
DENIED = 1
CHAT = 111111111


class FakeAPI:
    def __init__(self, token: str) -> None:
        self.token = token
        self.messages: list[tuple[int, str]] = []
        self.callbacks: list[str] = []

    def send_message(self, chat_id: int, text: str, reply_markup=None, parse_mode=None) -> None:
        self.messages.append((chat_id, text))

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        self.callbacks.append(callback_query_id)

    def set_my_commands(self) -> None:
        pass


class FakeFlow:
    mode = "normal"
    current_screen = "phone"

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.client = self

    def adb_connect(self) -> None:
        pass

    def create_session(self) -> str:
        return "fake-session"

    def launch_app(self) -> None:
        pass

    def close(self) -> None:
        pass

    def init_app(self) -> str:
        return "fake init ok"

    def prepare_phone_entry(self):
        self.current_screen = "phone"
        return self.describe_current_screen()

    def submit_phone(self, phone: str) -> str:
        if self.mode == "password_at_phone":
            self.current_screen = "password"
            return "password"
        self.current_screen = "code"
        return "code"

    def submit_code(self, code: str) -> str:
        if self.mode == "password_at_code":
            self.current_screen = "password"
            return "password"
        self.current_screen = "logged_in"
        return "logged_in"

    def submit_password(self, password: str) -> str:
        self.current_screen = "logged_in"
        return "logged_in"

    def read_profile(self) -> dict:
        return {
            "telegram_user_id": "123456",
            "username": "demo_user",
            "first_name": "Demo",
            "last_name": "Account",
            "raw_profile": "Demo Account\n@demo_user",
        }

    def sync_current_account(self) -> dict:
        self.current_screen = "logged_in"
        return self.read_profile()

    def describe_current_screen(self):
        kind = self.current_screen

        class Screen:
            def __init__(self, screen_kind):
                self.kind = screen_kind

            def bot_message(self_inner):
                if self_inner.kind == "phone":
                    return "当前页面要求输入手机号。\n\n页面文字：\n- Phone number"
                if self_inner.kind == "password":
                    return "当前页面要求输入两步验证密码。\n\n页面文字：\n- Password"
                if self_inner.kind == "logged_in":
                    return "当前页面看起来已经登录成功。"
                return "当前页面要求输入 Telegram 验证码。\n\n页面文字：\n- Code"

        return Screen(kind)


def update_message(text: str, user_id: int = ALLOWED, chat_id: int = CHAT) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": {"id": user_id},
            "chat": {"id": chat_id},
            "text": text,
        },
    }


def update_callback(data: str, user_id: int = ALLOWED, chat_id: int = CHAT) -> dict:
    return {
        "update_id": 2,
        "callback_query": {
            "id": f"cb-{data}",
            "from": {"id": user_id},
            "message": {"chat": {"id": chat_id}, "message_id": 1},
            "data": data,
        },
    }


def assert_last_contains(app: bot_module.BotApp, text: str) -> None:
    assert app.api.messages, "no bot messages captured"
    last = app.api.messages[-1][1]
    assert text in last, f"expected {text!r} in last message {last!r}"


def main() -> int:
    bot_module.TelegramXLoginFlow = FakeFlow
    app = bot_module.BotApp()
    fake_api = FakeAPI(app.cfg.bot_token)
    app.api = fake_api

    app.handle_update(update_message("/start"))
    assert len(fake_api.messages) >= 2
    assert "主菜单" in fake_api.messages[-2][1]

    app.handle_update(update_message("帮助"))
    assert_last_contains(app, "流程")

    app.handle_update(update_message("状态检查"))
    assert_last_contains(app, "环境状态")

    app.handle_update(update_message("账号列表"))
    assert_last_contains(app, "数据库里还没有")

    app.handle_update(update_callback("init_app"))
    assert_last_contains(app, "fake init ok")

    app.handle_update(update_callback("login_start"))
    assert app.states[ALLOWED]["step"] == "phone"
    assert_last_contains(app, "请输入这次要登录的手机号")

    app.handle_update(update_message("+8613800000000"))
    assert app.states[ALLOWED]["step"] == "code"
    assert_last_contains(app, "请根据页面提示输入 Telegram 验证码")

    app.handle_update(update_message("12345"))
    assert ALLOWED not in app.states
    assert_last_contains(app, "登录成功")
    rows = app.store.list_accounts()
    assert len(rows) == 1
    assert rows[0]["username"] == "demo_user"
    assert rows[0]["status"] == "logged_in"

    app.handle_update(update_callback("accounts"))
    assert_last_contains(app, "demo_user")

    app.handle_update(update_callback("sync_current"))
    assert_last_contains(app, "已同步当前登录账号")

    app.handle_update(update_callback("diagnose"))
    assert_last_contains(app, "当前页面")

    app.handle_update(update_message("登录账号"))
    assert app.states[ALLOWED]["step"] == "phone"
    app.handle_update(update_callback("cancel"))
    assert ALLOWED not in app.states
    assert_last_contains(app, "已取消")

    FakeFlow.mode = "password_at_code"
    app.handle_update(update_message("登录账号"))
    app.handle_update(update_message("+15551234567"))
    app.handle_update(update_message("99999"))
    assert app.states[ALLOWED]["step"] == "password"
    app.handle_update(update_message("secret"))
    assert ALLOWED not in app.states
    assert_last_contains(app, "登录成功")

    app.handle_update(update_message("/start", user_id=DENIED, chat_id=DENIED))
    assert fake_api.messages[-1] == (DENIED, "无权限操作。")

    print("OK bot interface tests passed")
    print(f"messages_captured={len(fake_api.messages)} db={app.cfg.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
