from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from urllib.error import URLError
from typing import Optional

from tgx_automation.actions import login as login_actions
from tgx_automation.actions import profile as profile_actions
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
    if code and local:
        phone = f"+{code} {local}"
    else:
        raw = account.get("phone_e164", "")
        phone = raw
    if full or len(phone) <= 7:
        return phone
    digits = re.sub(r"\D+", "", phone)
    if len(digits) <= 7:
        return phone
    masked = digits[:3] + "***" + digits[-4:]
    return "+" + masked


def _format_account(account: dict) -> str:
    name = " ".join(v for v in [account.get("first_name", ""), account.get("last_name", "")] if v)
    lines = [
        f"手机号: {_display_phone(account)}",
        f"状态: {account.get('status', 'unknown')}",
        f"用户名: @{account.get('username')}" if account.get("username") else "用户名: 未记录",
        f"名称: {name}" if name else "名称: 未记录",
        f"封禁: {'是' if account.get('is_banned') else '否'}",
        f"限制: {'是' if account.get('has_restrictions') else '否'}",
        f"切换序号: {account.get('switch_index')}",
    ]
    if account.get("restriction_note"):
        lines.append(f"限制说明: {account['restriction_note']}")
    return "\n".join(lines)


def _format_actions(account: dict, can_switch: bool) -> str:
    actions = ["可用操作: /state, /cancel"]
    actions.append(f"查看详情: /panel {account['phone_e164']}")
    if can_switch and account.get("switch_index") is not None:
        actions.append(f"切换到该账号: /switch {account['phone_e164']}")
        actions.append(f"触发链接: /deeplink {account['phone_e164']} <link>")
        actions.append(f"设置用户名: /setname {account['phone_e164']} <username>")
        actions.append(f"设置姓名: /setfullname {account['phone_e164']} <first> [last]")
        actions.append(f"设置头像: /setavatar {account['phone_e164']}")
    if can_switch:
        actions.append(f"强制重新登录: /relogin {account['phone_e164']}")
    return "\n".join(actions)


def _format_account_list(accounts: list[dict], full: bool = True) -> str:
    if not accounts:
        return "暂无账号。"
    lines = ["账号列表:"]
    for index, account in enumerate(accounts, 1):
        username = f"@{account['username']}" if account.get("username") else "-"
        name = " ".join(v for v in [account.get("first_name", ""), account.get("last_name", "")] if v) or "-"
        flags = []
        if account.get("is_banned"):
            flags.append("封禁")
        if account.get("has_restrictions"):
            flags.append("限制")
        flag_text = ",".join(flags) if flags else "正常"
        lines.append(
            f"{index}. {_display_phone(account, full=full)} | {username} | {name} | "
            f"{account.get('status', 'unknown')} | {flag_text} | switch={account.get('switch_index')}"
        )
    lines.append("")
    lines.append("这些字段用于: 判断账号是否已登录/需验证码/需密码、按手机号或 switch_index 切换账号、给管理员追踪封禁和限制状态、把普通用户只能关联到自己添加的账号。")
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


def _send_page_prompt(chat_id: int, adb: AdbClient, svc: AutomationService, pending: dict[int, str]) -> None:
    state = svc.debug_info()
    page = state.get("page", "unknown")
    elements = _page_elements(adb)
    if page == "login_code":
        pending[chat_id] = "code"
        _send_message(chat_id, "当前页面需要验证码。请直接发送验证码数字。\n页面元素:\n" + elements)
    elif page == "login_password":
        pending[chat_id] = "password"
        _send_message(chat_id, "当前页面需要二步验证密码。请直接发送密码。\n页面元素:\n" + elements)
    else:
        _send_message(chat_id, f"当前页面: {page}\n页面元素:\n{elements}")


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


def _range_accounts(store: AccountStore, start: str, count: str) -> list[dict]:
    accounts = store.list_accounts()
    start_index = max(int(start) - 1, 0)
    amount = max(int(count), 0)
    return accounts[start_index : start_index + amount]


def _switch_to_account(adb: AdbClient, store: AccountStore, account: dict) -> list[str]:
    if account.get("switch_index") is None:
        raise ValueError("该账号还没有 switch_index，暂不能切换")
    steps = switch_account_by_index(adb, int(account["switch_index"]))
    store.upsert_account(phone_e164=account["phone_e164"], mark_seen=True)
    return steps


def _sync_account_from_telegram(adb: AdbClient, store: AccountStore, account: dict) -> dict:
    fields = profile_actions.read_visible_profile_fields(adb)
    updates: dict = {"status": "active"}
    for key in ("username", "first_name", "last_name"):
        if fields.get(key):
            updates[key] = fields[key]
    if fields.get("phone"):
        digits = re.sub(r"\D+", "", fields["phone"])
        current_digits = re.sub(r"\D+", "", account.get("phone_e164", ""))
        if digits and digits == current_digits:
            updates["phone_e164"] = account["phone_e164"]
    return store.upsert_account(phone_e164=account["phone_e164"], mark_seen=True, **updates)


def _require_account(
    chat_id: int,
    sender_id: Optional[int],
    store: AccountStore,
    value: str,
    action: str,
) -> Optional[dict]:
    account = _find_account(store, value)
    if not account or not _account_visible(account, sender_id, chat_id):
        _send_message(chat_id, f"未找到账号，或你没有权限{action}。")
        return None
    return account


def _set_username(
    chat_id: int,
    sender_id: Optional[int],
    args: list[str],
    adb: AdbClient,
    svc: AutomationService,
    store: AccountStore,
) -> None:
    if len(args) < 2:
        _send_message(chat_id, "格式: /setname 号码/索引 用户名")
        return
    account = _require_account(chat_id, sender_id, store, args[0], "设置用户名")
    if not account:
        return
    username = args[1].lstrip("@")
    steps = _switch_to_account(adb, store, account)
    steps.extend(profile_actions.change_username_for_current_account(adb, username))
    fields = profile_actions.read_visible_profile_fields(adb)
    actual = fields.get("username")
    if actual != username:
        _send_message(
            chat_id,
            f"用户名未被 Telegram X 确认，数据库未更新。expected={username}, actual={actual or '-'}\n页面元素:\n"
            + _page_elements(adb),
        )
        return
    account = store.update_account(account["phone_e164"], {"username": actual}) or account
    _send_message(chat_id, "用户名已确认提交，数据库已更新。\n" + _format_account(account) + "\n步骤: " + " -> ".join(steps))


def _set_fullname(
    chat_id: int,
    sender_id: Optional[int],
    args: list[str],
    adb: AdbClient,
    svc: AutomationService,
    store: AccountStore,
) -> None:
    if len(args) < 2:
        _send_message(chat_id, "格式: /setfullname 号码/索引 firstname [lastname]")
        return
    account = _require_account(chat_id, sender_id, store, args[0], "设置姓名")
    if not account:
        return
    first_name = args[1]
    last_name = args[2] if len(args) > 2 else ""
    steps = _switch_to_account(adb, store, account)
    try:
        steps.extend(profile_actions.change_name(adb, first_name, last_name))
    except Exception as exc:
        _send_message(chat_id, f"姓名设置失败，数据库未更新：{exc}\n页面元素:\n" + _page_elements(adb))
        return
    state = svc.debug_info()
    if state.get("page") == "profile_edit":
        _send_message(chat_id, "姓名未确认成功，数据库未更新。\n页面元素:\n" + _page_elements(adb))
        return
    account = store.update_account(account["phone_e164"], {"first_name": first_name, "last_name": last_name}) or account
    _send_message(chat_id, "姓名已确认提交，数据库已更新。\n" + _format_account(account) + "\n步骤: " + " -> ".join(steps))


def _set_avatar(
    chat_id: int,
    sender_id: Optional[int],
    args: list[str],
    adb: AdbClient,
    svc: AutomationService,
    store: AccountStore,
) -> None:
    if len(args) < 1:
        _send_message(chat_id, "格式: /setavatar 号码/索引")
        return
    account = _require_account(chat_id, sender_id, store, args[0], "设置头像")
    if not account:
        return
    steps = _switch_to_account(adb, store, account)
    steps.extend(profile_actions.change_avatar_from_gallery(adb))
    state = svc.debug_info()
    if state.get("page") in {"unknown", "profile_edit"}:
        _send_message(chat_id, "头像操作已执行，但未能确认成功。数据库不会记录头像状态。\n页面元素:\n" + _page_elements(adb))
        return
    _send_message(chat_id, "头像设置流程已执行。\n" + _format_account(account) + "\n步骤: " + " -> ".join(steps))


def _set_avatar_all(
    chat_id: int,
    sender_id: Optional[int],
    args: list[str],
    adb: AdbClient,
    svc: AutomationService,
    store: AccountStore,
) -> None:
    if len(args) < 2:
        _send_message(chat_id, "格式: /setavatarall 起始账号编号 账号数")
        return
    if not _is_admin(sender_id):
        _send_message(chat_id, "只有管理员可以批量设置头像。")
        return
    accounts = _range_accounts(store, args[0], args[1])
    done = []
    for index, account in enumerate(accounts, 1):
        steps = _switch_to_account(adb, store, account)
        steps.extend(profile_actions.change_avatar_from_gallery(adb))
        state = svc.debug_info()
        status = "ok" if state.get("page") not in {"unknown", "profile_edit"} else "unconfirmed"
        done.append(f"{index}. {_display_phone(account)} {status} ({' -> '.join(steps)})")
    _send_message(chat_id, "批量头像流程完成:\n" + "\n".join(done)[:3200])


def _avatar_config(chat_id: int, args: list[str]) -> None:
    if not args or args[0] == "show":
        _send_message(chat_id, "当前头像来源: Telegram X 图库第一项。帖子链接预设尚未接入。")
        return
    if args[0] in {"set", "clear"}:
        _send_message(chat_id, "已收到头像配置命令，但帖子链接解析尚未接入；当前仍使用图库第一项。")
        return
    _send_message(chat_id, "格式: /avatarcfg show|set|clear [帖子链接]")


def _trigger_deeplink(
    chat_id: int,
    sender_id: Optional[int],
    args: list[str],
    adb: AdbClient,
    store: AccountStore,
) -> None:
    if len(args) < 2:
        _send_message(chat_id, "格式: /deeplink 号码/索引 deeplink")
        return
    account = _require_account(chat_id, sender_id, store, args[0], "触发 deeplink")
    if not account:
        return
    steps = _switch_to_account(adb, store, account)
    adb.open_deeplink(args[1])
    steps.append(f"open deeplink {args[1]}")
    _send_message(chat_id, "已触发 deeplink。\n" + _format_account(account) + "\n步骤: " + " -> ".join(steps))


def _trigger_deeplink_all(
    chat_id: int,
    sender_id: Optional[int],
    args: list[str],
    adb: AdbClient,
    store: AccountStore,
) -> None:
    if len(args) < 3:
        _send_message(chat_id, "格式: /deeplinkall 起始 数量 deeplink [间隔秒] [最大秒]")
        return
    if not _is_admin(sender_id):
        _send_message(chat_id, "只有管理员可以批量触发 deeplink。")
        return
    accounts = _range_accounts(store, args[0], args[1])
    delay_min = float(args[3]) if len(args) > 3 else 2.0
    delay_max = float(args[4]) if len(args) > 4 else delay_min
    done = []
    for index, account in enumerate(accounts, 1):
        steps = _switch_to_account(adb, store, account)
        adb.open_deeplink(args[2])
        done.append(f"{index}. {_display_phone(account)} ok ({' -> '.join(steps)})")
        if index < len(accounts):
            time.sleep(delay_max if delay_max > delay_min else delay_min)
    _send_message(chat_id, "批量 deeplink 完成:\n" + "\n".join(done)[:3200])


def _open_spambot(
    chat_id: int,
    sender_id: Optional[int],
    args: list[str],
    adb: AdbClient,
    store: AccountStore,
) -> None:
    if len(args) < 1:
        _send_message(chat_id, "格式: /spam 号码/索引")
        return
    account = _require_account(chat_id, sender_id, store, args[0], "打开 SpamBot")
    if not account:
        return
    steps = _switch_to_account(adb, store, account)
    adb.open_deeplink("https://t.me/SpamBot?start=start")
    steps.append("open @SpamBot")
    _send_message(chat_id, "已打开 @SpamBot，请查看 Telegram X 内回复。\n步骤: " + " -> ".join(steps))


def _sync_account_command(
    chat_id: int,
    sender_id: Optional[int],
    args: list[str],
    adb: AdbClient,
    store: AccountStore,
) -> None:
    if not args:
        _send_message(chat_id, "格式: /sync 号码/索引")
        return
    account = _require_account(chat_id, sender_id, store, args[0], "同步")
    if not account:
        return
    steps = _switch_to_account(adb, store, account)
    synced = _sync_account_from_telegram(adb, store, account)
    _send_message(
        chat_id,
        "已从当前 Telegram X 页面同步可读取字段。\n"
        + _format_account(synced)
        + "\n步骤: "
        + " -> ".join([*steps, "open settings", "read visible profile fields"]),
    )


def _handle_users_command(chat_id: int, sender_id: Optional[int], store: AccountStore) -> bool:
    accounts = store.list_accounts()
    if not _is_admin(sender_id):
        accounts = [a for a in accounts if _is_owner(a, sender_id, chat_id)]
    _send_message(chat_id, _format_account_list(accounts)[:3500])
    return True


def _handle_legacy_users_subcommand(
    chat_id: int,
    sender_id: Optional[int],
    text: str,
    adb: AdbClient,
    svc: AutomationService,
    store: AccountStore,
) -> bool:
    parts = text.split()
    if not parts or parts[0] != "/users":
        return False
    if len(parts) == 1:
        return _handle_users_command(chat_id, sender_id, store)
    legacy = {
        "panel": "/panel",
        "view": "/view",
        "detail": "/detail",
        "reconnectall": "/reconnectall",
        "sendcard": "/sendcard",
        "deeplink": "/deeplink",
        "deeplinkall": "/deeplinkall",
        "setname": "/setname",
        "setfullname": "/setfullname",
        "setavatar": "/setavatar",
        "setavatarall": "/setavatarall",
        "avatarcfg": "/avatarcfg",
        "spam": "/spam",
        "unspam": "/unspam",
    }
    sub = parts[1].lower()
    if sub in legacy:
        mapped = " ".join([legacy[sub], *parts[2:]])
        return _handle_top_level_command(chat_id, sender_id, mapped, adb, svc, store)
    if sub == "sync":
        mapped = " ".join(["/sync", *parts[2:]])
        return _handle_top_level_command(chat_id, sender_id, mapped, adb, svc, store)
    _send_message(chat_id, "这个 /users 子命令已移除，请使用顶层命令。发送 /users 查看账号列表。")
    return True

def _handle_top_level_command(
    chat_id: int,
    sender_id: Optional[int],
    text: str,
    adb: AdbClient,
    svc: AutomationService,
    store: AccountStore,
) -> bool:
    parts = text.split()
    if not parts:
        return False
    command = parts[0].lower()
    args = parts[1:]

    if command == "/panel":
        if not args:
            _send_message(chat_id, "格式: /panel 号码/索引")
            return True
        account = _require_account(chat_id, sender_id, store, args[0], "查看")
        if account:
            _send_message(chat_id, _format_account(account) + "\n" + _format_actions(account, True))
        return True

    if command == "/view":
        if not args:
            _send_message(chat_id, "格式: /view 号码/索引 [full]")
            return True
        account = _require_account(chat_id, sender_id, store, args[0], "查看")
        if account:
            full = len(args) > 1 and args[1].lower() == "full"
            _send_message(chat_id, _format_account_list([account], full=full))
        return True

    if command == "/detail":
        if not args:
            _send_message(chat_id, "格式: /detail 号码/索引")
            return True
        account = _require_account(chat_id, sender_id, store, args[0], "查看详情")
        if account:
            _send_message(chat_id, _format_account(account) + "\n" + _format_actions(account, True))
        return True

    if command == "/reconnectall":
        steps = recover_home(adb)
        _send_message(chat_id, "已重新载入 Telegram X 主界面。\n步骤: " + " -> ".join(steps))
        return True

    if command == "/sendcard":
        if not args:
            _send_message(chat_id, "格式: /sendcard url")
            return True
        _send_message(chat_id, args[0])
        return True

    if command == "/deeplink":
        _trigger_deeplink(chat_id, sender_id, args, adb, store)
        return True

    if command == "/deeplinkall":
        _trigger_deeplink_all(chat_id, sender_id, args, adb, store)
        return True

    if command == "/setname":
        _set_username(chat_id, sender_id, args, adb, svc, store)
        return True

    if command == "/setfullname":
        _set_fullname(chat_id, sender_id, args, adb, svc, store)
        return True

    if command == "/setavatar":
        _set_avatar(chat_id, sender_id, args, adb, svc, store)
        return True

    if command == "/setavatarall":
        _set_avatar_all(chat_id, sender_id, args, adb, svc, store)
        return True

    if command == "/avatarcfg":
        _avatar_config(chat_id, args)
        return True

    if command in {"/spam", "/unspam"}:
        _open_spambot(chat_id, sender_id, args, adb, store)
        return True

    if command == "/sync":
        _sync_account_command(chat_id, sender_id, args, adb, store)
        return True

    return False


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
        _send_message(chat_id, "缺少当前登录手机号上下文。请重新发送 /add_account，或对已有账号使用 /users panel 后选择 /relogin。")
        return
    if page == "login_password":
        pending[chat_id] = "password"
        _send_message(chat_id, "验证码已提交，当前需要二步验证密码。请直接发送密码。\n步骤: " + " -> ".join(steps))
        return
    if page == "login_code":
        pending[chat_id] = "code"
        _send_message(chat_id, "验证码提交后仍停留在验证码页，可能验证码错误或尚未跳转。请直接重新发送验证码。\n页面元素:\n" + _page_elements(adb))
        return

    pending.pop(chat_id, None)
    if phone_e164:
        meta = pending_account_meta.pop(chat_id, {})
        source_message = meta.pop("_message", {})
        account = store.upsert_account(
            phone_e164=phone_e164,
            status="active",
            mark_login=True,
            mark_seen=True,
            **meta,
        )
        account = _sync_account_from_telegram(adb, store, account)
        pending_phone.pop(chat_id, None)
        _notify_new_account(account, source_message, chat_id)
    _send_message(chat_id, f"验证码已提交，当前页面: {page}\n步骤: " + " -> ".join(steps))


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
        _send_page_prompt(chat_id, adb, svc, pending)
        return

    steps = login_actions.submit_password(adb, password)
    time.sleep(3)
    state = svc.debug_info()
    page = state.get("page")
    phone_e164 = pending_phone.get(chat_id)
    if not phone_e164:
        _send_message(chat_id, "缺少当前登录手机号上下文。请重新发送 /add_account，或对已有账号使用 /users panel 后选择 /relogin。")
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
    if phone_e164:
        meta = pending_account_meta.pop(chat_id, {})
        source_message = meta.pop("_message", {})
        account = store.upsert_account(
            phone_e164=phone_e164,
            status="active",
            mark_login=True,
            mark_seen=True,
            **meta,
        )
        account = _sync_account_from_telegram(adb, store, account)
        pending_phone.pop(chat_id, None)
        _notify_new_account(account, source_message, chat_id)
    _send_message(chat_id, f"二步验证密码已提交，当前页面: {page}\n步骤: " + " -> ".join(steps))


def run_polling() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run bot polling")

    adb = AdbClient(settings.adb_serial)
    svc = AutomationService(adb)
    store = AccountStore(settings.db_path)
    offset = 0
    pending: dict[int, str] = {}
    pending_phone: dict[int, str] = {}
    pending_force_login: dict[int, str] = {}
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
            try:
                message = update.get("message", {})
                text = message.get("text", "")
                contact = message.get("contact")
                chat_id = message.get("chat", {}).get("id")
                if not chat_id:
                    continue
                sender_id = message.get("from", {}).get("id")
                is_admin = _is_admin(sender_id)

                if _handle_top_level_command(chat_id, sender_id, text, adb, svc, store):
                    continue
                if text.startswith("/users"):
                    _handle_legacy_users_subcommand(chat_id, sender_id, text, adb, svc, store)
                elif text.startswith("/add_account"):
                    pending[chat_id] = "phone"
                    _request_phone(chat_id)
                elif contact and pending.get(chat_id) == "phone":
                    contact_user_id = contact.get("user_id")
                    if contact_user_id and sender_id and contact_user_id != sender_id:
                        _send_message(chat_id, "请共享你自己的手机号，不要转发其他联系人的号码。")
                        continue

                    phone_number = contact.get("phone_number", "")
                    country, code, phone = _parse_phone(phone_number)
                    if not code:
                        _send_message(chat_id, "暂时无法识别这个手机号的国家码，请联系管理员补充国家码映射。", _remove_keyboard())
                        pending.pop(chat_id, None)
                        continue

                    phone_e164 = AccountStore.normalize_phone(code, phone)
                    existing = store.get_account(phone_e164)
                    force_login = pending_force_login.get(chat_id) == phone_e164
                    if existing and not force_login:
                        pending.pop(chat_id, None)
                        pending_phone.pop(chat_id, None)
                        pending_force_login.pop(chat_id, None)
                        pending_account_meta.pop(chat_id, None)
                        _send_message(
                            chat_id,
                            "这个账号已经在系统中。\n"
                            + _format_account(existing)
                            + "\n"
                            + _format_actions(existing, _account_visible(existing, sender_id, chat_id)),
                            _remove_keyboard(),
                        )
                        continue

                    pending_force_login.pop(chat_id, None)
                    steps = open_add_account(adb)
                    steps.extend(login_actions.fill_phone(adb, country, code, phone))
                    pending[chat_id] = "code"
                    pending_phone[chat_id] = phone_e164
                    pending_account_meta[chat_id] = {
                        "country": country,
                        "country_code": code,
                        "local_phone": phone,
                        "username": message.get("from", {}).get("username"),
                        "first_name": contact.get("first_name") or message.get("from", {}).get("first_name"),
                        "last_name": contact.get("last_name") or message.get("from", {}).get("last_name"),
                        "added_by_chat_id": chat_id,
                        "added_by_user_id": message.get("from", {}).get("id"),
                        "_message": message,
                    }
                    _send_message(
                        chat_id,
                        "手机号已提交。收到验证码后请直接发送验证码数字。\n"
                        f"识别号码: +{code} {phone}\n"
                        f"步骤: {' -> '.join(steps)}\n"
                        f"页面元素:\n{_page_elements(adb)}",
                        _remove_keyboard(),
                    )
                elif text.startswith("/code"):
                    code = text.removeprefix("/code").strip().replace(" ", "")
                    if not code:
                        _send_message(chat_id, "请直接发送验证码数字。")
                        continue
                    _submit_code(chat_id, code, adb, svc, store, pending, pending_phone, pending_account_meta)
                elif text.startswith("/password"):
                    password = text.removeprefix("/password").strip()
                    if not password:
                        _send_message(chat_id, "请直接发送二步验证密码。")
                        continue
                    _submit_password(chat_id, password, adb, svc, store, pending, pending_phone, pending_account_meta)
                elif text.startswith("/cancel"):
                    pending.pop(chat_id, None)
                    pending_phone.pop(chat_id, None)
                    pending_force_login.pop(chat_id, None)
                    pending_account_meta.pop(chat_id, None)
                    _send_message(chat_id, "已取消当前添加账号流程。", _remove_keyboard())
                elif text.startswith("/whoami"):
                    _send_message(chat_id, f"你的 Telegram user id: {sender_id}\n管理员: {'是' if is_admin else '否'}")
                elif text.startswith("/relogin"):
                    arg = text.removeprefix("/relogin").strip()
                    if not arg:
                        _send_message(chat_id, "格式: /relogin +手机号 或 /relogin 序号")
                        continue
                    account = _find_account(store, arg)
                    if not account or not _account_visible(account, sender_id, chat_id):
                        _send_message(chat_id, "未找到账号，或你没有权限重新登录。")
                        continue
                    pending[chat_id] = "phone"
                    pending_phone.pop(chat_id, None)
                    pending_force_login[chat_id] = account["phone_e164"]
                    _send_message(
                        chat_id,
                        "将重新登录这个账号。请点击按钮共享手机号继续。\n"
                        + _format_account(account),
                        {
                            "keyboard": [[{"text": "共享手机号", "request_contact": True}]],
                            "one_time_keyboard": True,
                            "resize_keyboard": True,
                        },
                    )
                elif text.startswith("/switch"):
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
                elif text.startswith("/state"):
                    state = svc.debug_info()
                    _send_message(chat_id, json.dumps(state, ensure_ascii=False)[:2500] + "\n页面元素:\n" + _page_elements(adb))
                elif text.startswith("/recover"):
                    steps = recover_home(adb)
                    _send_message(chat_id, "recover: " + " -> ".join(steps))
                elif pending.get(chat_id) == "code" and text.strip():
                    code = re.sub(r"\D+", "", text)
                    if not code:
                        _send_message(chat_id, "当前需要验证码，请直接发送验证码数字。")
                        continue
                    _submit_code(chat_id, code, adb, svc, store, pending, pending_phone, pending_account_meta)
                elif pending.get(chat_id) == "password" and text.strip():
                    _submit_password(chat_id, text.strip(), adb, svc, store, pending, pending_phone, pending_account_meta)
                elif text.strip() and svc.debug_info().get("page") == "login_code":
                    code = re.sub(r"\D+", "", text)
                    if code:
                        _submit_code(chat_id, code, adb, svc, store, pending, pending_phone, pending_account_meta)
                    else:
                        _send_page_prompt(chat_id, adb, svc, pending)
                elif text.strip() and svc.debug_info().get("page") == "login_password":
                    _submit_password(chat_id, text.strip(), adb, svc, store, pending, pending_phone, pending_account_meta)
                else:
                    _send_message(
                        chat_id,
                        "commands: /add_account /users /panel /switch /sync /setname /setfullname /setavatar /deeplink /spam /state /recover /cancel\n"
                        "登录中可直接发送验证码或密码，不需要加命令。",
                    )
            except Exception as exc:
                print(f"telegram update error: {exc}", flush=True)
                if message.get("chat", {}).get("id"):
                    _send_message(message["chat"]["id"], f"执行失败: {exc}")

        time.sleep(1)


if __name__ == "__main__":
    run_polling()
