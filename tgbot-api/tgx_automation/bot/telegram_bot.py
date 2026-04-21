from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from typing import Optional
from urllib.error import URLError

from tgx_automation.actions import login as login_actions
from tgx_automation.actions.navigation import open_add_account, recover_home, switch_account_by_index
from tgx_automation.adb_client import AdbClient
from tgx_automation.config import settings
from tgx_automation.service import AutomationService
from tgx_automation.storage import AccountStore
from tgx_automation.ui_xml import parse_nodes


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


def _send_message(chat_id: int, text: str, reply_markup: Optional[dict] = None) -> None:
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    _tg_post("sendMessage", payload)


def _request_phone(chat_id: int) -> None:
    _send_message(
        chat_id,
        "请点击下面的按钮共享手机号，用于添加 Telegram X 账号。",
        {
            "keyboard": [[{"text": "共享手机号", "request_contact": True}]],
            "one_time_keyboard": True,
            "resize_keyboard": True,
        },
    )


def _remove_keyboard() -> dict:
    return {"remove_keyboard": True}


def _parse_phone(raw_phone: str) -> tuple[str, str, str]:
    digits = re.sub(r"\D+", "", raw_phone)
    country_by_code = {
        "1": "USA",
        "7": "Russia",
        "44": "United Kingdom",
        "49": "Germany",
        "60": "Malaysia",
        "61": "Australia",
        "65": "Singapore",
        "81": "Japan",
        "86": "China",
        "91": "India",
        "94": "Sri Lanka",
    }
    for code in sorted(country_by_code, key=len, reverse=True):
        if digits.startswith(code):
            return country_by_code[code], code, digits[len(code) :]
    return "", "", digits


def _is_admin(user_id: Optional[int]) -> bool:
    return bool(user_id and user_id in settings.telegram_admin_ids)


def _is_owner(account: dict, user_id: Optional[int], chat_id: int) -> bool:
    return bool(
        (user_id and account.get("added_by_user_id") == user_id)
        or account.get("added_by_chat_id") == chat_id
    )


def _account_visible(account: dict, user_id: Optional[int], chat_id: int) -> bool:
    return _is_admin(user_id) or _is_owner(account, user_id, chat_id)


def _display_phone(account: dict, full: bool = True) -> str:
    code = account.get("country_code", "")
    local = account.get("local_phone", "")
    phone = f"+{code} {local}" if code and local else account.get("phone_e164", "")
    if full:
        return phone
    digits = re.sub(r"\D+", "", phone)
    if len(digits) <= 7:
        return phone
    return "+" + digits[:3] + "***" + digits[-4:]


def _format_account(account: dict) -> str:
    lines = [
        f"手机号: {_display_phone(account)}",
        f"状态: {account.get('status', 'unknown')}",
        f"封禁: {'是' if account.get('is_banned') else '否'}",
        f"限制: {'是' if account.get('has_restrictions') else '否'}",
        f"切换序号: {account.get('switch_index')}",
        f"最近登录: {account.get('last_login_at') or '-'}",
        f"最近检查: {account.get('last_seen_at') or '-'}",
    ]
    if account.get("restriction_note"):
        lines.append(f"限制说明: {account['restriction_note']}")
    return "\n".join(lines)


def _format_account_list(accounts: list[dict], full: bool = True) -> str:
    if not accounts:
        return "暂无账号。"
    lines = ["账号列表:"]
    for index, account in enumerate(accounts, 1):
        flags = []
        if account.get("is_banned"):
            flags.append("封禁")
        if account.get("has_restrictions"):
            flags.append("限制")
        flag_text = ",".join(flags) if flags else "正常"
        lines.append(
            f"{index}. {_display_phone(account, full=full)} | "
            f"{account.get('status', 'unknown')} | {flag_text} | switch={account.get('switch_index')}"
        )
    return "\n".join(lines)


def _format_user(message: dict) -> str:
    user = message.get("from", {})
    parts = [
        f"id={user.get('id', '-')}",
        f"name={' '.join(v for v in [user.get('first_name', ''), user.get('last_name', '')] if v) or '-'}",
    ]
    if user.get("username"):
        parts.append(f"username=@{user['username']}")
    return " | ".join(parts)


def _notify_admins(text: str, exclude_chat_id: Optional[int] = None) -> None:
    for admin_id in settings.telegram_admin_ids:
        if exclude_chat_id and admin_id == exclude_chat_id:
            continue
        try:
            _send_message(admin_id, text)
        except Exception as exc:
            print(f"admin notify error: {admin_id}: {exc}", flush=True)


def _notify_new_account(account: dict, message: dict, chat_id: int) -> None:
    _notify_admins(
        "新用户添加账号成功:\n"
        f"用户: {_format_user(message)}\n"
        f"Chat ID: {chat_id}\n"
        + _format_account(account),
        exclude_chat_id=chat_id,
    )


def _page_elements(adb: AdbClient, limit: int = 12) -> str:
    xml = adb.dump_ui_xml()
    items: list[str] = []
    seen: set[str] = set()
    for node in parse_nodes(xml):
        label = node.text or node.content_desc
        rid = node.resource_id.rsplit("/", 1)[-1] if node.resource_id else ""
        if not label and not rid:
            continue
        center = node.center
        parts = []
        if label:
            parts.append(label[:60])
        if rid and rid not in {"app_root", "content"}:
            parts.append(f"id={rid}")
        if center:
            parts.append(f"@{center[0]},{center[1]}")
        line = " | ".join(parts)
        if line in seen:
            continue
        seen.add(line)
        items.append(line)
        if len(items) >= limit:
            break
    return "\n".join(items) if items else "未提取到可读元素"


def _find_account(store: AccountStore, phone_or_index: str) -> Optional[dict]:
    value = phone_or_index.strip()
    if value.isdigit():
        for account in store.list_accounts():
            if str(account.get("switch_index")) == value:
                return account
            digits = re.sub(r"\D+", "", account.get("phone_e164", ""))
            if digits == value:
                return account
    if not value.startswith("+") and value.replace(" ", "").isdigit():
        value = "+" + value.replace(" ", "")
    return store.get_account(value)


def _current_login_requirement(svc: AutomationService) -> str:
    state = svc.debug_info()
    page = state.get("page")
    if page in {"add_account", "login_phone"}:
        return "phone"
    if page == "login_code":
        return "code"
    if page == "login_password":
        return "password"
    if page == "login_email":
        return "email_or_email_code"
    return "inspect"


def _visible_accounts(store: AccountStore, sender_id: Optional[int], chat_id: int) -> list[dict]:
    accounts = store.list_accounts()
    if _is_admin(sender_id):
        return accounts
    return [account for account in accounts if _is_owner(account, sender_id, chat_id)]


def _submit_code(
    chat_id: int,
    code: str,
    adb: AdbClient,
    svc: AutomationService,
    store: AccountStore,
    pending: dict[int, str],
    pending_phone: dict[int, str],
    pending_account_meta: dict[int, dict],
) -> None:
    steps = login_actions.submit_code(adb, code)
    time.sleep(2)
    state = svc.debug_info()
    page = state.get("page")
    phone_e164 = pending_phone.get(chat_id)
    if not phone_e164:
        _send_message(chat_id, "缺少当前登录手机号上下文。请重新发送 /add_account。")
        return
    if page == "login_password":
        pending[chat_id] = "password"
        store.upsert_account(phone_e164=phone_e164, status="needs_password", mark_seen=True)
        _send_message(chat_id, "验证码已提交，当前需要二步验证密码。请直接发送密码。\n步骤: " + " -> ".join(steps))
        return
    if page == "login_code":
        pending[chat_id] = "code"
        _send_message(chat_id, "验证码提交后仍停留在验证码页，可能验证码错误或尚未跳转。请直接重新发送验证码。\n页面元素:\n" + _page_elements(adb))
        return

    pending.pop(chat_id, None)
    meta = pending_account_meta.pop(chat_id, {})
    source_message = meta.pop("_message", {})
    account = store.upsert_account(
        phone_e164=phone_e164,
        status="active",
        mark_login=True,
        mark_seen=True,
        **meta,
    )
    pending_phone.pop(chat_id, None)
    _notify_new_account(account, source_message, chat_id)
    _send_message(chat_id, f"验证码已提交，当前页面: {page}\n" + _format_account(account) + "\n步骤: " + " -> ".join(steps))


def _submit_password(
    chat_id: int,
    password: str,
    adb: AdbClient,
    svc: AutomationService,
    store: AccountStore,
    pending: dict[int, str],
    pending_phone: dict[int, str],
    pending_account_meta: dict[int, dict],
) -> None:
    state_before = svc.debug_info()
    if state_before.get("page") != "login_password":
        _send_message(chat_id, f"当前页面不是 2FA 密码页: {state_before.get('page')}\n页面元素:\n" + _page_elements(adb))
        return

    steps = login_actions.submit_password(adb, password)
    time.sleep(3)
    state = svc.debug_info()
    page = state.get("page")
    phone_e164 = pending_phone.get(chat_id)
    if not phone_e164:
        _send_message(chat_id, "缺少当前登录手机号上下文。请重新发送 /add_account。")
        return
    if page == "login_password":
        pending[chat_id] = "password"
        _send_message(chat_id, "密码提交后仍停留在二步验证页，可能密码错误。请直接重新发送密码。\n页面元素:\n" + _page_elements(adb))
        return
    if page == "login_code":
        pending[chat_id] = "code"
        _send_message(chat_id, "当前回到验证码页，请直接发送验证码。\n页面元素:\n" + _page_elements(adb))
        return

    pending.pop(chat_id, None)
    meta = pending_account_meta.pop(chat_id, {})
    source_message = meta.pop("_message", {})
    account = store.upsert_account(
        phone_e164=phone_e164,
        status="active",
        mark_login=True,
        mark_seen=True,
        **meta,
    )
    pending_phone.pop(chat_id, None)
    _notify_new_account(account, source_message, chat_id)
    _send_message(chat_id, f"二步验证密码已提交，当前页面: {page}\n" + _format_account(account) + "\n步骤: " + " -> ".join(steps))


def run_polling() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run bot polling")

    adb = AdbClient(settings.adb_serial)
    svc = AutomationService(adb)
    store = AccountStore(settings.db_path)
    offset = 0
    pending: dict[int, str] = {}
    pending_phone: dict[int, str] = {}
    pending_account_meta: dict[int, dict] = {}
    _tg_get("deleteWebhook?drop_pending_updates=false")

    while True:
        try:
            data = _tg_get(f"getUpdates?timeout=25&offset={offset}")
        except URLError as exc:
            print(f"telegram polling error: {exc}", flush=True)
            time.sleep(5)
            continue

        for update in data.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message", {})
            try:
                text = message.get("text", "")
                contact = message.get("contact")
                chat_id = message.get("chat", {}).get("id")
                if not chat_id:
                    continue
                sender_id = message.get("from", {}).get("id")

                if text.startswith("/add_account") or text.startswith("/start"):
                    pending[chat_id] = "phone"
                    _request_phone(chat_id)
                    continue

                if contact and pending.get(chat_id) == "phone":
                    contact_user_id = contact.get("user_id")
                    if contact_user_id and sender_id and contact_user_id != sender_id:
                        _send_message(chat_id, "请共享你自己的手机号，不要转发其他联系人的号码。")
                        continue

                    country, code, phone = _parse_phone(contact.get("phone_number", ""))
                    if not code:
                        _send_message(chat_id, "暂时无法识别这个手机号的国家码，请联系管理员补充国家码映射。", _remove_keyboard())
                        pending.pop(chat_id, None)
                        continue

                    phone_e164 = AccountStore.normalize_phone(code, phone)
                    existing = store.get_account(phone_e164)
                    if existing:
                        pending.pop(chat_id, None)
                        pending_phone.pop(chat_id, None)
                        pending_account_meta.pop(chat_id, None)
                        _send_message(chat_id, "这个账号已经在系统中。\n" + _format_account(existing), _remove_keyboard())
                        continue

                    steps = open_add_account(adb)
                    if _current_login_requirement(svc) != "phone":
                        _send_message(
                            chat_id,
                            "打开添加账号后没有进入手机号输入页。Telegram X 可能正在恢复一个未完成登录流程，"
                            "请先完成或取消当前登录。\n页面元素:\n" + _page_elements(adb),
                            _remove_keyboard(),
                        )
                        pending.pop(chat_id, None)
                        continue
                    steps.extend(login_actions.fill_phone(adb, country, code, phone))
                    pending[chat_id] = "code"
                    pending_phone[chat_id] = phone_e164
                    pending_account_meta[chat_id] = {
                        "country": country,
                        "country_code": code,
                        "local_phone": phone,
                        "added_by_chat_id": chat_id,
                        "added_by_user_id": sender_id,
                        "_message": message,
                    }
                    store.upsert_account(
                        phone_e164=phone_e164,
                        country=country,
                        country_code=code,
                        local_phone=phone,
                        status="code_sent",
                        added_by_chat_id=chat_id,
                        added_by_user_id=sender_id,
                        mark_seen=True,
                    )
                    _send_message(
                        chat_id,
                        "手机号已提交。收到验证码后请直接发送验证码数字。\n"
                        f"识别号码: +{code} {phone}\n"
                        f"步骤: {' -> '.join(steps)}\n"
                        f"页面元素:\n{_page_elements(adb)}",
                        _remove_keyboard(),
                    )
                    continue

                if text.startswith("/users"):
                    _send_message(chat_id, _format_account_list(_visible_accounts(store, sender_id, chat_id))[:3500])
                    continue

                if text.startswith("/state"):
                    state = svc.debug_info()
                    _send_message(chat_id, json.dumps(state, ensure_ascii=False)[:2500] + "\n页面元素:\n" + _page_elements(adb))
                    continue

                if text.startswith("/switch"):
                    arg = text.removeprefix("/switch").strip()
                    if not arg:
                        _send_message(chat_id, "格式: /switch +手机号 或 /switch 序号")
                        continue
                    account = _find_account(store, arg)
                    if not account or not _account_visible(account, sender_id, chat_id):
                        _send_message(chat_id, "未找到账号，或你没有权限切换。")
                        continue
                    if account.get("switch_index") is None:
                        _send_message(chat_id, "该账号还没有 switch_index，暂不能切换。")
                        continue
                    steps = switch_account_by_index(adb, int(account["switch_index"]))
                    store.upsert_account(phone_e164=account["phone_e164"], mark_seen=True)
                    _send_message(chat_id, "已切换。\n" + _format_account(account) + "\n步骤: " + " -> ".join(steps))
                    continue

                if text.startswith("/recover"):
                    steps = recover_home(adb)
                    _send_message(chat_id, "recover: " + " -> ".join(steps))
                    continue

                if text.startswith("/cancel"):
                    pending.pop(chat_id, None)
                    pending_phone.pop(chat_id, None)
                    pending_account_meta.pop(chat_id, None)
                    _send_message(chat_id, "已取消当前添加账号流程。", _remove_keyboard())
                    continue

                if text.startswith("/whoami"):
                    _send_message(chat_id, f"你的 Telegram user id: {sender_id}\n管理员: {'是' if _is_admin(sender_id) else '否'}")
                    continue

                if text.startswith("/code"):
                    code = text.removeprefix("/code").strip().replace(" ", "")
                    if not code:
                        _send_message(chat_id, "请直接发送验证码数字。")
                        continue
                    _submit_code(chat_id, code, adb, svc, store, pending, pending_phone, pending_account_meta)
                    continue

                if text.startswith("/password"):
                    password = text.removeprefix("/password").strip()
                    if not password:
                        _send_message(chat_id, "请直接发送二步验证密码。")
                        continue
                    _submit_password(chat_id, password, adb, svc, store, pending, pending_phone, pending_account_meta)
                    continue

                if pending.get(chat_id) == "code" and text.strip():
                    code = re.sub(r"\D+", "", text)
                    if not code:
                        _send_message(chat_id, "当前需要验证码，请直接发送验证码数字。")
                        continue
                    _submit_code(chat_id, code, adb, svc, store, pending, pending_phone, pending_account_meta)
                    continue

                if pending.get(chat_id) == "password" and text.strip():
                    _submit_password(chat_id, text.strip(), adb, svc, store, pending, pending_phone, pending_account_meta)
                    continue

                _send_message(
                    chat_id,
                    "commands: /add_account /users /switch /state /recover /cancel /whoami\n"
                    "登录中可直接发送验证码或密码，不需要加命令。",
                )
            except Exception as exc:
                print(f"telegram update error: {exc}", flush=True)
                if message.get("chat", {}).get("id"):
                    _send_message(message["chat"]["id"], f"执行失败: {exc}")

        time.sleep(1)


if __name__ == "__main__":
    run_polling()
