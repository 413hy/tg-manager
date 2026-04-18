from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from tgx_automation.actions.navigation import recover_home
from tgx_automation.adb_client import AdbClient
from tgx_automation.config import settings
from tgx_automation.service import AutomationService


def _tg_get(path: str) -> dict:
    with urllib.request.urlopen(f"https://api.telegram.org/bot{settings.telegram_bot_token}/{path}") as r:
        return json.loads(r.read().decode())


def _tg_post(path: str, payload: dict) -> dict:
    body = urllib.parse.urlencode(payload).encode()
    with urllib.request.urlopen(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/{path}",
        data=body,
    ) as r:
        return json.loads(r.read().decode())


def run_polling() -> None:
    adb = AdbClient(settings.adb_serial)
    svc = AutomationService(adb)
    offset = 0

    while True:
        data = _tg_get(f"getUpdates?timeout=25&offset={offset}")
        for update in data.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message", {})
            text = message.get("text", "")
            chat_id = message.get("chat", {}).get("id")
            if not chat_id:
                continue

            if text.startswith("/state"):
                state = svc.debug_info()
                _tg_post("sendMessage", {"chat_id": chat_id, "text": json.dumps(state, ensure_ascii=False)[:3500]})
            elif text.startswith("/recover"):
                steps = recover_home(adb)
                _tg_post("sendMessage", {"chat_id": chat_id, "text": "recover: " + " -> ".join(steps)})
            else:
                _tg_post("sendMessage", {"chat_id": chat_id, "text": "commands: /state /recover"})

        time.sleep(1)


if __name__ == "__main__":
    run_polling()
