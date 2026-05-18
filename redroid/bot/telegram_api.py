#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


class TelegramAPI:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"

    def request(self, method: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{self.base_url}/{method}", data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
        parsed = json.loads(body)
        if not parsed.get("ok"):
            raise RuntimeError(f"Telegram API error on {method}: {parsed}")
        return parsed

    def get_updates(self, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        return self.request("getUpdates", payload, timeout=timeout + 10).get("result", [])

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        self.request("sendMessage", payload)

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        self.request("answerCallbackQuery", payload)

    def set_my_commands(self) -> None:
        self.request(
            "setMyCommands",
            {
                "commands": [
                    {"command": "start", "description": "打开主菜单"},
                    {"command": "status", "description": "查看环境和账号状态"},
                    {"command": "accounts", "description": "查看已登录账号"},
                    {"command": "cancel", "description": "取消当前操作"},
                ]
            },
        )


def reply_menu() -> dict[str, Any]:
    return {
        "keyboard": [
            [{"text": "初始化应用"}, {"text": "登录账号"}],
            [{"text": "更换手机号"}, {"text": "取消当前操作"}],
            [{"text": "同步当前账号"}, {"text": "页面诊断"}],
            [{"text": "账号列表"}, {"text": "状态检查"}],
            [{"text": "帮助"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def main_inline_menu() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "初始化应用", "callback_data": "init_app"},
                {"text": "登录账号", "callback_data": "login_start"},
            ],
            [
                {"text": "更换手机号", "callback_data": "login_start"},
                {"text": "取消当前操作", "callback_data": "cancel"},
            ],
            [
                {"text": "同步当前账号", "callback_data": "sync_current"},
                {"text": "页面诊断", "callback_data": "diagnose"},
            ],
            [
                {"text": "账号列表", "callback_data": "accounts"},
                {"text": "状态检查", "callback_data": "status"},
            ],
        ]
    }


def cancel_inline() -> dict[str, Any]:
    return {"inline_keyboard": [[{"text": "取消当前操作", "callback_data": "cancel"}]]}


def quote_code(text: str) -> str:
    return urllib.parse.quote(text, safe="")
