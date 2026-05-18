#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import traceback
from typing import Any

from .appium_client import AppiumError
from .config import get_config
from .db import AccountStore
from .login_flow import TelegramXLoginFlow
from .telegram_api import TelegramAPI, cancel_inline, main_inline_menu, reply_menu


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


class BotApp:
    def __init__(self) -> None:
        self.cfg = get_config()
        self.api = TelegramAPI(self.cfg.bot_token)
        self.store = AccountStore(self.cfg.db_path)
        self.states: dict[int, dict[str, Any]] = {}
        self.running = True

    def run_cmd(self, cmd: list[str], timeout: int = 30) -> tuple[int, str]:
        result = subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=timeout)
        return result.returncode, (result.stdout + result.stderr).strip()

    def is_allowed(self, user_id: int) -> bool:
        return user_id == self.cfg.allowed_user_id

    def send_menu(self, chat_id: int) -> None:
        self.api.send_message(
            chat_id,
            "主菜单：请选择要执行的操作。",
            reply_markup=reply_menu(),
        )
        self.api.send_message(
            chat_id,
            "快捷操作：",
            reply_markup=main_inline_menu(),
        )

    def unauthorized(self, chat_id: int) -> None:
        self.api.send_message(chat_id, "无权限操作。")

    def status_text(self) -> str:
        code, health = self.run_cmd(["/root/redroid/scripts/healthcheck.sh"], timeout=45)
        stats = self.store.stats()
        lines = [
            "环境状态：",
            health or ("健康检查失败" if code else "健康检查通过"),
            "",
            "账号统计：",
            f"总数：{stats.get('total', 0)}",
            f"已登录：{stats.get('logged_in', 0)}",
            f"其他状态：{sum(v for k, v in stats.items() if k not in {'total', 'logged_in'})}",
        ]
        return "\n".join(lines)

    def accounts_text(self) -> str:
        rows = self.store.list_accounts(limit=20)
        if not rows:
            return "数据库里还没有登录成功的账号。"
        lines = ["最近登录成功账号："]
        for row in rows:
            username = f"@{row['username']}" if row["username"] else "-"
            name = " ".join(x for x in [row["first_name"], row["last_name"]] if x) or "-"
            lines.append(
                f"#{row['id']} phone={row['phone'] or '-'} user_id={row['telegram_user_id'] or '-'} "
                f"username={username} name={name} status={row['status']} last_seen={row['last_seen_at'] or '-'}"
            )
        return "\n".join(lines)

    def parse_account_line(self, text: str) -> dict[str, str]:
        parts = text.strip().split()
        profile = {
            "telegram_user_id": "",
            "username": "",
            "first_name": "",
            "last_name": "",
            "raw_profile": f"manual_register: {text.strip()}",
        }
        phone = ""
        name_parts: list[str] = []
        for part in parts:
            if part.startswith("+") and any(ch.isdigit() for ch in part):
                phone = part
            elif part.startswith("@"):
                profile["username"] = part.lstrip("@")
            elif part.isdigit() and len(part) >= 5:
                profile["telegram_user_id"] = part
            else:
                name_parts.append(part)
        if name_parts:
            profile["first_name"] = " ".join(name_parts)
        return {"phone": phone, **profile}

    def sync_current_account(self, chat_id: int, user_id: int) -> None:
        self.api.send_message(chat_id, "正在检查 Telegram X 当前是否已登录。")
        flow = TelegramXLoginFlow(self.cfg)
        try:
            profile = flow.sync_current_account()
            screen_text = self.safe_screen_text(flow)
            if profile.get("username") or profile.get("telegram_user_id"):
                self.store.upsert_account(profile, None, status="logged_in")
                self.store.record_event(None, "logged_in", "synced current account automatically")
                self.api.send_message(chat_id, "已同步当前登录账号。\n\n" + self.accounts_text(), reply_markup=reply_menu())
                return

            self.states[user_id] = {"step": "manual_register", "raw_profile": profile.get("raw_profile", "")}
            self.api.send_message(
                chat_id,
                "已确认 Telegram X 当前处于登录状态，但这个 Telegram X 版本没有把手机号/用户名稳定暴露给 Appium。\n\n"
                + screen_text
                + "\n\n请发送一行账号资料用于入库，格式：\n"
                + "+8613800000000 @username 昵称\n\n"
                + "没有用户名可以只发手机号和昵称。",
                reply_markup=cancel_inline(),
            )
        except Exception as exc:
            self.api.send_message(chat_id, f"同步当前账号失败：{exc}", reply_markup=reply_menu())
        finally:
            flow.close()

    def handle_manual_register(self, chat_id: int, user_id: int, text: str) -> None:
        state = self.states.get(user_id, {})
        data = self.parse_account_line(text)
        phone = data.pop("phone", "")
        if not phone and not data.get("username") and not data.get("telegram_user_id"):
            self.api.send_message(chat_id, "至少需要手机号、用户名或 Telegram user_id 中的一个。请重新发送。", reply_markup=cancel_inline())
            return
        if state.get("raw_profile"):
            data["raw_profile"] = state["raw_profile"] + "\n\n" + data.get("raw_profile", "")
        self.store.upsert_account(data, phone or None, status="logged_in")
        self.store.record_event(phone or None, "logged_in", "manual account registration after current-session sync")
        self.states.pop(user_id, None)
        self.api.send_message(chat_id, "已登记当前登录账号。\n\n" + self.accounts_text(), reply_markup=reply_menu())

    def diagnose_page(self, chat_id: int) -> None:
        flow = TelegramXLoginFlow(self.cfg)
        try:
            flow.client.adb_connect()
            flow.client.launch_app()
            flow.client.create_session()
            screen = flow.describe_current_screen()
            self.api.send_message(chat_id, screen.bot_message(), reply_markup=reply_menu())
        except Exception as exc:
            self.api.send_message(chat_id, f"页面诊断失败：{exc}", reply_markup=reply_menu())
        finally:
            flow.close()

    def start_login(self, chat_id: int, user_id: int) -> None:
        self.api.send_message(chat_id, "正在准备新的手机号登录页，请稍等。")
        flow = TelegramXLoginFlow(self.cfg)
        try:
            screen = flow.prepare_phone_entry()
            screen_text = screen.bot_message()
            self.states[user_id] = {"step": "phone"}
            self.api.send_message(
                chat_id,
                screen_text
                + "\n\n请输入这次要登录的手机号，格式示例：+8613800000000。"
                + "\n如果页面里还残留旧手机号，直接发送新手机号即可，Bot 会覆盖旧内容。",
                reply_markup=cancel_inline(),
            )
        except Exception as exc:
            self.states[user_id] = {"step": "phone"}
            self.api.send_message(
                chat_id,
                f"准备手机号页失败：{exc}\n\n请输入要登录的手机号，格式示例：+8613800000000。",
                reply_markup=cancel_inline(),
            )
        finally:
            flow.close()

    def cancel(self, chat_id: int, user_id: int) -> None:
        self.states.pop(user_id, None)
        self.api.send_message(chat_id, "已取消当前操作。", reply_markup=reply_menu())

    def handle_phone(self, chat_id: int, user_id: int, phone: str) -> None:
        self.states[user_id] = {"step": "submitting_phone", "phone": phone}
        self.store.record_event(phone, "phone_submitted", "operator submitted phone")
        self.api.send_message(chat_id, "正在打开 Telegram X 并提交手机号，请稍等。")
        flow = TelegramXLoginFlow(self.cfg)
        try:
            state = flow.submit_phone(phone)
            screen_text = self.safe_screen_text(flow)
            if state == "password":
                self.states[user_id] = {"step": "password", "phone": phone}
                self.api.send_message(chat_id, screen_text + "\n\n请根据页面提示输入两步验证密码。", reply_markup=cancel_inline())
            elif state == "logged_in":
                profile = flow.read_profile()
                self.store.upsert_account(profile, phone, status="logged_in")
                self.store.record_event(phone, "logged_in", "already logged in after phone submit")
                self.states.pop(user_id, None)
                self.api.send_message(chat_id, "登录成功，账号已记录进数据库。\n\n" + self.accounts_text(), reply_markup=reply_menu())
            elif state == "code":
                self.states[user_id] = {"step": "code", "phone": phone}
                self.api.send_message(chat_id, screen_text + "\n\n请根据页面提示输入 Telegram 验证码。", reply_markup=cancel_inline())
            else:
                self.states[user_id] = {"step": state, "phone": phone}
                self.api.send_message(chat_id, screen_text + f"\n\n当前识别状态：{state}。请根据页面提示回复下一步内容。", reply_markup=cancel_inline())
        except Exception as exc:
            self.store.record_event(phone, "phone_failed", str(exc))
            self.states[user_id] = {"step": "phone"}
            self.api.send_message(chat_id, f"提交手机号失败：{exc}\n请确认应用页面后重新输入手机号。", reply_markup=cancel_inline())
        finally:
            flow.close()

    def handle_code(self, chat_id: int, user_id: int, code: str) -> None:
        state = self.states.get(user_id, {})
        phone = state.get("phone")
        self.api.send_message(chat_id, "正在提交验证码并确认登录状态。")
        flow = TelegramXLoginFlow(self.cfg)
        try:
            result = flow.submit_code(code)
            screen_text = self.safe_screen_text(flow)
            if result == "password":
                self.states[user_id] = {"step": "password", "phone": phone}
                self.api.send_message(chat_id, screen_text + "\n\n请根据页面提示输入两步验证密码。", reply_markup=cancel_inline())
                return
            if result != "logged_in":
                self.store.record_event(phone, "code_waiting", result)
                self.api.send_message(chat_id, screen_text + f"\n\n验证码已提交，但尚未确认登录成功。当前识别状态：{result}。")
                return
            profile = flow.read_profile()
            self.store.upsert_account(profile, phone, status="logged_in")
            self.store.record_event(phone, "logged_in", "login completed")
            self.states.pop(user_id, None)
            self.api.send_message(chat_id, "登录成功，账号已记录进数据库。\n\n" + self.accounts_text(), reply_markup=reply_menu())
        except Exception as exc:
            self.store.record_event(phone, "code_failed", str(exc))
            self.api.send_message(chat_id, f"验证码处理失败：{exc}", reply_markup=cancel_inline())
        finally:
            flow.close()

    def handle_password(self, chat_id: int, user_id: int, password: str) -> None:
        state = self.states.get(user_id, {})
        phone = state.get("phone")
        self.api.send_message(chat_id, "正在提交两步验证密码。")
        flow = TelegramXLoginFlow(self.cfg)
        try:
            result = flow.submit_password(password)
            screen_text = self.safe_screen_text(flow)
            if result != "logged_in":
                self.store.record_event(phone, "password_waiting", result)
                self.api.send_message(chat_id, screen_text + f"\n\n密码已提交，但尚未确认登录成功。当前识别状态：{result}。", reply_markup=cancel_inline())
                return
            profile = flow.read_profile()
            self.store.upsert_account(profile, phone, status="logged_in")
            self.store.record_event(phone, "logged_in", "login completed with password")
            self.states.pop(user_id, None)
            self.api.send_message(chat_id, "登录成功，账号已记录进数据库。\n\n" + self.accounts_text(), reply_markup=reply_menu())
        except Exception as exc:
            self.store.record_event(phone, "password_failed", str(exc))
            self.api.send_message(chat_id, f"两步验证处理失败：{exc}", reply_markup=cancel_inline())
        finally:
            flow.close()

    def safe_screen_text(self, flow: TelegramXLoginFlow) -> str:
        try:
            screen = flow.describe_current_screen()
            return screen.bot_message()
        except Exception as exc:
            return f"无法读取当前页面数据：{exc}"

    def init_app(self, chat_id: int) -> None:
        self.api.send_message(chat_id, "正在初始化 Telegram X 应用。")
        flow = TelegramXLoginFlow(self.cfg)
        try:
            message = flow.init_app()
            self.api.send_message(chat_id, message, reply_markup=reply_menu())
        except Exception as exc:
            self.api.send_message(chat_id, f"初始化失败：{exc}", reply_markup=reply_menu())
        finally:
            flow.close()

    def handle_text(self, chat_id: int, user_id: int, text: str) -> None:
        if text in {"/start", "菜单", "主菜单"}:
            self.send_menu(chat_id)
            return
        if text == "/cancel":
            self.cancel(chat_id, user_id)
            return
        if text in {"/status", "状态检查"}:
            self.api.send_message(chat_id, self.status_text(), reply_markup=reply_menu())
            return
        if text in {"/accounts", "账号列表"}:
            self.api.send_message(chat_id, self.accounts_text(), reply_markup=reply_menu())
            return
        if text in {"同步当前账号"}:
            self.sync_current_account(chat_id, user_id)
            return
        if text in {"页面诊断"}:
            self.diagnose_page(chat_id)
            return
        if text in {"初始化应用"}:
            self.init_app(chat_id)
            return
        if text in {"登录账号", "更换手机号"}:
            self.start_login(chat_id, user_id)
            return
        if text in {"取消当前操作"}:
            self.cancel(chat_id, user_id)
            return
        if text in {"帮助"}:
            self.api.send_message(
                chat_id,
                "流程：初始化应用 -> 登录账号 -> 输入手机号 -> 输入验证码 -> 必要时输入两步验证密码 -> 登录成功后自动入库。",
                reply_markup=reply_menu(),
            )
            return

        state = self.states.get(user_id, {})
        step = state.get("step")
        if step == "phone":
            self.handle_phone(chat_id, user_id, text.strip())
        elif step == "code":
            self.handle_code(chat_id, user_id, text.strip())
        elif step == "password":
            self.handle_password(chat_id, user_id, text)
        elif step == "manual_register":
            self.handle_manual_register(chat_id, user_id, text)
        else:
            self.api.send_message(chat_id, "请选择菜单操作。", reply_markup=reply_menu())

    def handle_callback(self, callback: dict[str, Any]) -> None:
        query_id = callback["id"]
        user_id = int(callback["from"]["id"])
        message = callback.get("message") or {}
        chat_id = int(message.get("chat", {}).get("id", user_id))
        data = callback.get("data", "")
        self.api.answer_callback_query(query_id)
        if not self.is_allowed(user_id):
            self.unauthorized(chat_id)
            return
        mapping = {
            "init_app": "初始化应用",
            "login_start": "登录账号",
            "accounts": "账号列表",
            "status": "状态检查",
            "sync_current": "同步当前账号",
            "diagnose": "页面诊断",
            "cancel": "/cancel",
        }
        self.handle_text(chat_id, user_id, mapping.get(data, data))

    def handle_update(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            self.handle_callback(update["callback_query"])
            return
        message = update.get("message")
        if not message:
            return
        user = message.get("from") or {}
        user_id = int(user.get("id", 0))
        chat_id = int(message["chat"]["id"])
        if not self.is_allowed(user_id):
            self.unauthorized(chat_id)
            return
        text = message.get("text", "")
        self.handle_text(chat_id, user_id, text.strip())

    def stop(self, *_: object) -> None:
        self.running = False

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        self.api.set_my_commands()
        offset: int | None = None
        logging.info("tg-redroid-bot started")
        while self.running:
            try:
                updates = self.api.get_updates(offset, self.cfg.poll_timeout)
                for update in updates:
                    offset = int(update["update_id"]) + 1
                    self.handle_update(update)
            except Exception:
                logging.error("bot loop error\n%s", traceback.format_exc())


def main() -> int:
    app = BotApp()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
