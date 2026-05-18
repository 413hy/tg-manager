from __future__ import annotations

import shlex
import asyncio
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telethon.errors import PasswordHashInvalidError, SessionPasswordNeededError
from telethon.errors import (
    FloodWaitError,
    PhoneCodeEmptyError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberBannedError,
    PhoneNumberInvalidError,
)
from telethon import functions

from app.bot.auth import AdminOnlyMiddleware
from app.bot.formatting import COMMANDS, account_line
from app.bot.keyboards import (
    account_actions_panel,
    accounts_panel,
    avatar_panel,
    batch_panel,
    cancel_inline,
    force_reply,
    home_panel,
    main_menu,
    monitor_panel,
    privacy_keys_panel,
    privacy_rules_panel,
    profile_edit_panel,
    remove_keyboard,
    settings_panel,
    twofa_panel,
)
from app.bot.states import ExportSessionFlow, ImportSessionFlow, LoginFlow, ProfileEditFlow, TwoFAEditFlow
from app.config import settings
from app.db.models import (
    AccountSecurity,
    Admin,
    AllowedTarget,
    PrivacySettings,
    RateLimit,
    SpamCheck,
    TgAccount,
    TgSession,
    Job,
)
from app.services.crypto import decrypt_text
from app.services.audit import audit
from app.services.jobs import add_job_item, create_job, finish_job
from app.services.rate_limit import RateGate, get_rate
from app.services.targets import require_allowed_target
from app.tg import account_ops, batch_ops
from app.tg.client_pool import ClientPool

router = Router()
router.message.middleware(AdminOnlyMiddleware())
router.callback_query.middleware(AdminOnlyMiddleware())


MENU_TEXTS = {
    "系统状态": "status",
    "账号管理": "accounts",
    "登录账号": "login",
    "导入Session": "import_session",
    "导出Session": "export_session",
    "批量任务": "batch",
    "目标与速率": "settings",
    "监控中心": "monitor",
    "隐藏键盘": "hide",
}

CANCEL_TEXTS = {"取消", "取消当前操作", "/cancel"}

TEMPLATES = {
    "send": "/send <账号ID> <授权目标> <文本>",
    "subscribe": "/subscribe <账号ID> <授权目标>",
    "react": "/react <账号ID> <授权目标> <消息ID> <emoji>",
    "view_post": "/view_post <账号ID> <授权目标> <消息ID>",
    "forward": "/forward <账号ID> <源目标> <消息ID> <接收目标>",
    "target_add": "/target_allowlist add channel @your_test_channel 测试频道",
    "rate_set": "/rate set batch 5 60 2 6",
}

RANDOM_AVATAR_URLS = [
    "https://api.btstu.cn/sjbz/api.php?lx=dongman&format=images",
    "https://api.btstu.cn/sjbz/api.php?lx=meizi&format=images",
    "https://img.xjh.me/random_img.php?return=302&type=bg&ctype=acg",
    "https://picsum.photos/1200/1200.jpg",
    "https://picsum.photos/1024/1024.jpg",
]


class EmailCodeRequired(Exception):
    def __init__(self, code_length: int):
        self.code_length = code_length
        super().__init__(f"email confirmation code required: {code_length}")


def split_hint_email(parts: list[str], hint_index: int) -> tuple[str | None, str | None]:
    if len(parts) <= hint_index:
        return None, None
    tail = parts[hint_index:]
    email = None
    if tail and "@" in tail[-1]:
        email = tail.pop()
    hint = " ".join(tail) or None
    return hint, email


def require_email_code(code_length: int) -> str:
    raise EmailCodeRequired(code_length)


def args(message: Message) -> list[str]:
    text = message.text or ""
    try:
        return shlex.split(text)[1:]
    except ValueError:
        return text.split()[1:]


async def get_account(session: AsyncSession, account_id: int) -> TgAccount:
    account = await session.get(TgAccount, account_id)
    if not account:
        raise ValueError(f"账号 {account_id} 不存在")
    return account


async def resolve_account_id(session: AsyncSession, raw_id: str | int) -> int:
    value = int(raw_id)
    if -(2**31) <= value <= 2**31 - 1:
        account = await session.get(TgAccount, value)
        if account is not None:
            return account.id
    account = await session.scalar(select(TgAccount).where(TgAccount.user_id == value))
    if account is not None:
        return account.id
    raise ValueError(f"账号 {value} 不存在。本命令支持本地账号ID或 Telegram ID。")


async def account_ids_from_range(session: AsyncSession, start_id: int, count: int) -> list[int]:
    rows = await session.scalars(
        select(TgAccount.id)
        .join(TgSession, TgSession.account_id == TgAccount.id)
        .where(TgAccount.id >= start_id, TgSession.is_active.is_(True))
        .order_by(TgAccount.id)
        .limit(count)
    )
    return list(rows.all())


def parse_account_selection(value: str) -> list[int]:
    tokens = [token.strip() for token in value.replace("，", ",").replace(" ", ",").split(",")]
    account_ids: list[int] = []
    seen: set[int] = set()
    for token in tokens:
        if not token:
            continue
        if "-" in token:
            start_raw, end_raw = token.split("-", 1)
            start_id, end_id = int(start_raw), int(end_raw)
            if start_id > end_id:
                start_id, end_id = end_id, start_id
            values = range(start_id, end_id + 1)
        else:
            values = [int(token)]
        for account_id in values:
            if account_id not in seen:
                seen.add(account_id)
                account_ids.append(account_id)
    if not account_ids:
        raise ValueError("没有识别到账号ID")
    return account_ids


async def build_session_export(session: AsyncSession, account_ids: list[int]) -> tuple[str, int, list[str]]:
    lines = [
        "# Telethon StringSession export",
        f"# generated_at={datetime.now(timezone.utc).isoformat()}",
        "# 警告：string_session 等同于账号登录凭证，请不要发给不可信的人。",
        "# 导入时使用 phone 和 string_session 两项。",
        "",
    ]
    exported = 0
    skipped: list[str] = []
    for account_id in account_ids:
        account = await session.get(TgAccount, account_id)
        if account is None:
            skipped.append(f"#{account_id}: 账号不存在")
            continue
        tg_session = await session.scalar(
            select(TgSession)
            .where(TgSession.account_id == account.id, TgSession.is_active.is_(True))
            .order_by(TgSession.id.desc())
            .limit(1)
        )
        if tg_session is None:
            skipped.append(f"#{account.id}: 没有 active session")
            continue
        try:
            phone = decrypt_text(account.phone_encrypted) or account.phone_masked
            session_str = decrypt_text(tg_session.session_encrypted)
        except Exception as exc:
            skipped.append(f"#{account.id}: 解密失败 {exc}")
            continue
        if not session_str:
            skipped.append(f"#{account.id}: session 为空")
            continue
        exported += 1
        lines.extend(
            [
                "[account]",
                f"account_id={account.id}",
                f"telegram_user_id={account.user_id or ''}",
                f"username={('@' + account.username) if account.username else ''}",
                f"phone={phone}",
                f"phone_masked={account.phone_masked}",
                "session_type=telethon_string",
                f"string_session={session_str}",
                "",
            ]
        )
    if skipped:
        lines.append("[skipped]")
        lines.extend(skipped)
        lines.append("")
    return "\n".join(lines), exported, skipped


async def send_session_export(
    message: Message,
    sessionmaker: async_sessionmaker[AsyncSession],
    account_ids: list[int],
) -> None:
    async with sessionmaker() as session:
        content, exported, skipped = await build_session_export(session, account_ids)
    if exported == 0:
        await message.answer("没有可导出的 active session。\n" + ("\n".join(skipped) if skipped else ""))
        return
    if len(account_ids) == 1:
        filename = f"tg_session_{account_ids[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    else:
        filename = f"tg_sessions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    document = BufferedInputFile(content.encode("utf-8"), filename=filename)
    caption = f"已导出 {exported} 个 active session。文件包含敏感登录凭证，请妥善保存。"
    if skipped:
        caption += f"\n跳过 {len(skipped)} 个账号，详情见文件底部。"
    await message.answer_document(document, caption=caption[:1024])


async def status_text(
    sessionmaker: async_sessionmaker[AsyncSession],
    client_pool: ClientPool,
) -> str:
    async with sessionmaker() as session:
        total = await session.scalar(select(func.count()).select_from(TgAccount))
        usable = await session.scalar(
            select(func.count(func.distinct(TgSession.account_id))).where(TgSession.is_active.is_(True))
        )
    return (
        "系统状态\n"
        "Bot: OK\n"
        f"账号: {total or 0}\n"
        f"可连接账号: {usable or 0}\n"
        f"已连接: {len(client_pool.clients)}\n"
        f"时间: {datetime.now(timezone.utc).isoformat()}"
    )


async def accounts_text_and_rows(sessionmaker: async_sessionmaker[AsyncSession]) -> tuple[str, list[TgAccount]]:
    async with sessionmaker() as session:
        rows = await session.scalars(select(TgAccount).order_by(TgAccount.id).limit(100))
        accounts_list = list(rows.all())
    lines = [account_line(row) for row in accounts_list]
    return "账号列表\n" + ("\n".join(lines) if lines else "暂无账号"), accounts_list


async def account_detail_text(session: AsyncSession, account_id: int) -> str:
    account = await get_account(session, account_id)
    security = await session.get(AccountSecurity, account.id)
    privacy = await session.get(PrivacySettings, account.id)
    return "\n".join(
        [
            account_line(account),
            f"user_id: {account.user_id or '-'}",
            f"2FA: {'yes' if security and security.has_2fa else 'no/unknown'}",
            f"privacy: {privacy.rules_json if privacy else '{}'}",
            f"last_error: {account.last_error or '-'}",
        ]
    )


def account_status_label(status: str | None) -> str:
    labels = {
        "normal": "正常",
        "limited": "限制",
        "banned": "封禁",
        "unknown": "未知",
        "active": "未检测",
        "new": "未检测",
    }
    return labels.get(status or "unknown", status or "未知")


async def account_full_detail_text(
    session: AsyncSession,
    account_id: int,
    live_2fa: dict[str, str | bool | None] | None = None,
) -> str:
    account = await get_account(session, account_id)
    security = await session.get(AccountSecurity, account.id)
    privacy = await session.get(PrivacySettings, account.id)
    latest_spam = await session.scalar(
        select(SpamCheck)
        .where(SpamCheck.account_id == account.id)
        .order_by(desc(SpamCheck.checked_at), desc(SpamCheck.id))
        .limit(1)
    )
    active_session = await session.scalar(
        select(TgSession.id)
        .where(TgSession.account_id == account.id, TgSession.is_active.is_(True))
        .order_by(TgSession.id.desc())
        .limit(1)
    )
    local_email = decrypt_text(security.email_encrypted) if security and security.email_encrypted else None
    live_email = str(live_2fa.get("email_pattern")) if live_2fa and live_2fa.get("email_pattern") else None
    email = local_email or live_email
    has_2fa = bool(live_2fa.get("has_2fa")) if live_2fa and "has_2fa" in live_2fa else bool(security and security.has_2fa)
    twofa_hint = live_2fa.get("hint") if live_2fa else None
    spam_status = latest_spam.status_detected if latest_spam else account.status
    return "\n".join(
        [
            f"账号 #{account.id}",
            f"Telegram ID: {account.user_id or '-'}",
            f"用户名: @{account.username}" if account.username else "用户名: -",
            f"姓名: {' '.join(part for part in [account.first_name, account.last_name] if part) or '-'}",
            f"手机号: {account.phone_masked}",
            f"绑定邮箱: {email or '-'}",
            f"邮箱来源: {'本地保存' if local_email else ('Telegram 脱敏' if live_email else '-')}",
            f"本地 session: {'可用' if active_session else '不可用'}",
            f"账号状态: {account_status_label(spam_status)}",
            f"SpamBot 检测: {account_status_label(latest_spam.status_detected) if latest_spam else '未检测'}",
            f"SpamBot 时间: {latest_spam.checked_at.isoformat() if latest_spam else '-'}",
            f"SpamBot 原文: {(latest_spam.response_text or '-')[:1200] if latest_spam else '-'}",
            f"2FA: {'已启用' if has_2fa else '未启用/未知'}",
            f"2FA 提示: {twofa_hint or '-'}",
            f"隐私快照: {privacy.rules_json if privacy else '{}'}",
            f"最后登录: {account.last_login_at.isoformat() if account.last_login_at else '-'}",
            f"最后错误: {account.last_error or '-'}",
        ]
    )


async def answer_panel(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(text, reply_markup=reply_markup)


async def ask_with_cancel(message: Message, text: str, placeholder: str) -> None:
    await message.answer(f"{text}\n\n可随时点击“取消当前操作”。", reply_markup=cancel_inline())


async def ask_callback_with_cancel(callback: CallbackQuery, text: str, placeholder: str) -> None:
    await callback.answer()
    if callback.message:
        await ask_with_cancel(callback.message, text, placeholder)


def download_url_to_file(url: str, path: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "tg-account-bot/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        path.write_bytes(response.read())
    header = path.read_bytes()[:16]
    if not (
        header.startswith(b"\xff\xd8\xff")
        or header.startswith(b"\x89PNG")
        or header.startswith(b"RIFF")
        or header.startswith(b"GIF8")
    ):
        raise ValueError("接口返回的不是可识别图片")


@router.message(Command("start"))
async def start(message: Message) -> None:
    await message.answer("Telegram 多账号管理 Bot", reply_markup=main_menu())
    await message.answer("请选择管理入口。", reply_markup=home_panel())


@router.message(Command("cancel"))
@router.message(F.text.in_(CANCEL_TEXTS))
async def cancel_current(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    client = data.get("client")
    if client is not None:
        try:
            await client.disconnect()
        except Exception:
            pass
    await state.clear()
    await message.answer("已取消当前操作。", reply_markup=main_menu())
    await message.answer("请选择管理入口。", reply_markup=home_panel())


@router.callback_query(F.data == "flow:cancel")
async def cancel_current_callback(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    client = data.get("client")
    if client is not None:
        try:
            await client.disconnect()
        except Exception:
            pass
    await state.clear()
    await callback.answer("已取消")
    if callback.message:
        await callback.message.answer("已取消当前操作。", reply_markup=main_menu())
        await callback.message.answer("请选择管理入口。", reply_markup=home_panel())


@router.message(Command("cmd", "help", "command"))
async def cmd(message: Message) -> None:
    await message.answer(COMMANDS[:4096], reply_markup=main_menu())
    if len(COMMANDS) > 4096:
        await message.answer(COMMANDS[4096:])


@router.message(Command("status"))
async def status(message: Message, sessionmaker: async_sessionmaker[AsyncSession], client_pool: ClientPool) -> None:
    await message.answer(await status_text(sessionmaker, client_pool), reply_markup=home_panel())


@router.message(Command("login"))
async def login_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(LoginFlow.phone)
    await ask_with_cancel(message, "请输入手机号，格式如 +8613800000000", "+8613800000000")


@router.message(LoginFlow.phone)
async def login_phone(
    message: Message,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    phone = (message.text or "").strip()
    phone_masked = account_ops.mask_phone(phone)
    async with sessionmaker() as session:
        candidates = list(
            (
                await session.scalars(select(TgAccount).where(TgAccount.phone_masked == phone_masked))
            ).all()
        )
        existing = next(
            (
                account
                for account in candidates
                if decrypt_text(account.phone_encrypted) == phone
            ),
            None,
        )
        if existing is not None:
            await state.clear()
            await message.answer(
                f"该手机号已登录：账号 #{existing.id} {existing.phone_masked}",
                reply_markup=main_menu(),
            )
            await message.answer("账号操作", reply_markup=account_actions_panel(existing.id))
            return
    try:
        client, phone_code_hash = await account_ops.start_login(phone)
    except PhoneNumberInvalidError:
        await state.set_state(LoginFlow.phone)
        await ask_with_cancel(message, "手机号格式无效，请重新输入。", "+8613800000000")
        return
    except PhoneNumberBannedError:
        await state.clear()
        await message.answer("这个手机号被 Telegram 标记为不可登录/封禁，请换一个手机号。", reply_markup=main_menu())
        return
    except FloodWaitError as exc:
        await state.set_state(LoginFlow.phone)
        await ask_with_cancel(message, f"请求过于频繁，需要等待 {exc.seconds} 秒后再试。", "+8613800000000")
        return
    except Exception as exc:
        await state.set_state(LoginFlow.phone)
        await ask_with_cancel(message, f"发送验证码失败：{exc}\n请检查手机号后重试。", "+8613800000000")
        return
    await state.update_data(phone=phone, phone_code_hash=phone_code_hash, client=client)
    await state.set_state(LoginFlow.code)
    await ask_with_cancel(message, "验证码已发送，请输入验证码。", "Telegram 验证码")


@router.message(LoginFlow.code)
async def login_code(message: Message, state: FSMContext, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    data = await state.get_data()
    try:
        session_str, me = await account_ops.complete_login(
            phone=data["phone"],
            code=(message.text or "").strip(),
            phone_code_hash=data["phone_code_hash"],
            password=None,
            transient_client=data["client"],
        )
    except SessionPasswordNeededError:
        hint = "-"
        try:
            twofa_info = await account_ops.get_2fa_info(data["client"])
            hint = str(twofa_info.get("hint") or "-")
        except Exception:
            pass
        await state.set_state(LoginFlow.password)
        await ask_with_cancel(message, f"该账号需要 2FA 密码，请输入。\n密码提示：{hint}", "2FA 密码")
        return
    except (PhoneCodeInvalidError, PhoneCodeEmptyError):
        await state.set_state(LoginFlow.code)
        await ask_with_cancel(message, "验证码错误，请重新输入。", "Telegram 验证码")
        return
    except PhoneCodeExpiredError:
        client = data.get("client")
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
        await state.clear()
        await message.answer("验证码已过期，请重新开始登录。", reply_markup=main_menu())
        await message.answer("请选择管理入口。", reply_markup=home_panel())
        return
    except FloodWaitError as exc:
        await state.set_state(LoginFlow.code)
        await ask_with_cancel(message, f"尝试过于频繁，需要等待 {exc.seconds} 秒后再输入验证码。", "Telegram 验证码")
        return
    except Exception as exc:
        await state.set_state(LoginFlow.code)
        await ask_with_cancel(message, f"登录校验失败：{exc}\n请重新输入验证码，或取消后重新登录。", "Telegram 验证码")
        return
    async with sessionmaker() as session:
        account = await account_ops.save_logged_in_account(session, data["phone"], session_str, me)
    await state.clear()
    await message.answer(f"登录完成：账号ID #{account.id} {account.phone_masked}", reply_markup=main_menu())
    await message.answer("账号操作", reply_markup=account_actions_panel(account.id))


@router.message(LoginFlow.password)
async def login_password(message: Message, state: FSMContext, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    data = await state.get_data()
    password = (message.text or "").strip()
    try:
        session_str, me = await account_ops.complete_password_login(data["client"], password)
    except PasswordHashInvalidError:
        hint = "-"
        try:
            twofa_info = await account_ops.get_2fa_info(data["client"])
            hint = str(twofa_info.get("hint") or "-")
        except Exception:
            pass
        await state.set_state(LoginFlow.password)
        await ask_with_cancel(message, f"2FA 密码错误，请重新输入。\n密码提示：{hint}", "2FA 密码")
        return
    except FloodWaitError as exc:
        await state.set_state(LoginFlow.password)
        await ask_with_cancel(message, f"尝试过于频繁，需要等待 {exc.seconds} 秒后再输入 2FA 密码。", "2FA 密码")
        return
    except Exception as exc:
        await state.set_state(LoginFlow.password)
        await ask_with_cancel(message, f"2FA 校验失败：{exc}\n请重新输入，或取消后重新登录。", "2FA 密码")
        return
    async with sessionmaker() as session:
        account = await account_ops.save_logged_in_account(session, data["phone"], session_str, me, password)
    await state.clear()
    await message.answer(f"登录完成：账号ID #{account.id} {account.phone_masked}", reply_markup=main_menu())
    await message.answer("账号操作", reply_markup=account_actions_panel(account.id))


@router.message(Command("import_session"))
async def import_session_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ImportSessionFlow.phone)
    await ask_with_cancel(message, "请输入该 session 对应手机号。", "+8613800000000")


@router.message(ImportSessionFlow.phone)
async def import_session_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=(message.text or "").strip())
    await state.set_state(ImportSessionFlow.session)
    await ask_with_cancel(message, "请输入 Telethon StringSession。", "StringSession")


@router.message(ImportSessionFlow.session)
async def import_session_value(message: Message, state: FSMContext, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    data = await state.get_data()
    async with sessionmaker() as session:
        account = await account_ops.import_session(session, data["phone"], (message.text or "").strip())
    await state.clear()
    await message.answer(f"导入完成：账号ID #{account.id} {account.phone_masked}", reply_markup=main_menu())
    await message.answer("账号操作", reply_markup=account_actions_panel(account.id))


@router.message(Command("export_session"))
async def export_session(message: Message, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    a = args(message)
    if not a:
        await message.answer("用法：/export_session <账号ID或Telegram ID>")
        return
    try:
        async with sessionmaker() as session:
            account_id = await resolve_account_id(session, a[0])
        await send_session_export(message, sessionmaker, [account_id])
    except Exception as exc:
        await message.answer(f"导出失败：{exc}")


@router.message(Command("export_sessions"))
async def export_sessions(message: Message, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    a = args(message)
    if not a:
        await message.answer("用法：/export_sessions <账号ID列表> 或 /export_sessions <start_id> <count>\n例：/export_sessions 1,3,5-8")
        return
    try:
        async with sessionmaker() as session:
            if len(a) >= 2 and a[0].isdigit() and a[1].isdigit():
                account_ids = await account_ids_from_range(session, int(a[0]), int(a[1]))
            else:
                account_ids = parse_account_selection(" ".join(a))
                account_ids = [await resolve_account_id(session, account_id) for account_id in account_ids]
        await send_session_export(message, sessionmaker, account_ids)
    except Exception as exc:
        await message.answer(f"导出失败：{exc}")


@router.message(Command("export_session_select"))
async def export_session_select(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ExportSessionFlow.selection)
    await ask_with_cancel(message, "请输入要导出的账号ID，支持 1,3,5-8。", "1,3,5-8")


@router.message(ExportSessionFlow.selection)
async def export_session_selection(
    message: Message,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    try:
        selected = parse_account_selection((message.text or "").strip())
        async with sessionmaker() as session:
            account_ids = [await resolve_account_id(session, account_id) for account_id in selected]
        await send_session_export(message, sessionmaker, account_ids)
        await state.clear()
        await message.answer("导出流程已结束。", reply_markup=main_menu())
    except Exception as exc:
        await state.set_state(ExportSessionFlow.selection)
        await ask_with_cancel(message, f"账号ID格式不正确或账号不存在：{exc}\n请重新输入。", "1,3,5-8")


@router.message(Command("accounts"))
async def accounts(message: Message, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    text, accounts_list = await accounts_text_and_rows(sessionmaker)
    await message.answer(text, reply_markup=accounts_panel(accounts_list))


@router.message(Command("account", "profile"))
async def account_detail(message: Message, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    a = args(message)
    if not a:
        await message.answer("用法：/account <id>")
        return
    async with sessionmaker() as session:
        account_id = await resolve_account_id(session, a[0])
        text = await account_detail_text(session, account_id)
    await message.answer(text, reply_markup=account_actions_panel(account_id))


@router.message(Command("account_info", "account_detail"))
async def account_info(message: Message, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    a = args(message)
    if not a:
        await message.answer("用法：/account_info <id>")
        return
    async with sessionmaker() as session:
        account_id = await resolve_account_id(session, a[0])
        text = await account_full_detail_text(session, account_id)
    await message.answer(text[:4096], reply_markup=account_actions_panel(account_id))


@router.message(Command("reconnect"))
async def reconnect(message: Message, sessionmaker: async_sessionmaker[AsyncSession], client_pool: ClientPool) -> None:
    a = args(message)
    if not a:
        await message.answer("用法：/reconnect <id>")
        return
    async with sessionmaker() as session:
        account_id = await resolve_account_id(session, a[0])
        account = await get_account(session, account_id)
        client = await client_pool.get_client(account.id)
        await account_ops.sync_me(session, account, client)
    await message.answer(f"重连成功：#{account_id}")


@router.message(Command("reconnect_all", "service_monitor_on"))
async def reconnect_all(message: Message, client_pool: ClientPool) -> None:
    await client_pool.connect_all_active()
    await message.answer(f"已连接可用 session 账号：{len(client_pool.clients)}")


@router.message(Command("service_monitor_off"))
async def monitor_off(message: Message, client_pool: ClientPool) -> None:
    await client_pool.disconnect_all()
    await message.answer("已断开所有实时监听。")


@router.message(Command("set_name"))
async def set_name(message: Message, sessionmaker: async_sessionmaker[AsyncSession], client_pool: ClientPool) -> None:
    a = args(message)
    if len(a) < 2:
        await message.answer("用法：/set_name <id> <first> [last]")
        return
    async with sessionmaker() as session:
        account_id = await resolve_account_id(session, a[0])
        account = await get_account(session, account_id)
        client = await client_pool.get_client(account_id)
        await account_ops.set_name(client, a[1], a[2] if len(a) > 2 else None)
        await account_ops.sync_me(session, account, client)
    await message.answer("姓名已更新。")


@router.message(Command("set_bio"))
async def set_bio(message: Message, sessionmaker: async_sessionmaker[AsyncSession], client_pool: ClientPool) -> None:
    a = args(message)
    if len(a) < 2:
        await message.answer("用法：/set_bio <id> <bio>")
        return
    async with sessionmaker() as session:
        account_id = await resolve_account_id(session, a[0])
    client = await client_pool.get_client(account_id)
    await account_ops.set_bio(client, " ".join(a[1:]))
    await message.answer("简介已更新。")


@router.message(Command("set_username"))
async def set_username(message: Message, sessionmaker: async_sessionmaker[AsyncSession], client_pool: ClientPool) -> None:
    a = args(message)
    if len(a) != 2:
        await message.answer("用法：/set_username <id> <username>")
        return
    async with sessionmaker() as session:
        account_id = await resolve_account_id(session, a[0])
        account = await get_account(session, account_id)
        client = await client_pool.get_client(account_id)
        await account_ops.set_username(client, a[1].lstrip("@"))
        await account_ops.sync_me(session, account, client)
    await message.answer("用户名已更新。")


@router.message(Command("set_avatar"))
async def set_avatar(message: Message, sessionmaker: async_sessionmaker[AsyncSession], client_pool: ClientPool) -> None:
    a = args(message)
    if len(a) != 2:
        await message.answer("用法：/set_avatar <id> <服务器文件路径>")
        return
    async with sessionmaker() as session:
        account_id = await resolve_account_id(session, a[0])
    client = await client_pool.get_client(account_id)
    await account_ops.set_avatar(client, a[1])
    await message.answer("头像已更新。")


@router.message(Command("privacy"))
async def privacy(message: Message, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    a = args(message)
    if len(a) != 1:
        await message.answer("用法：/privacy <id>")
        return
    async with sessionmaker() as session:
        account_id = await resolve_account_id(session, a[0])
        row = await session.get(PrivacySettings, account_id)
    await message.answer(f"隐私快照：{row.rules_json if row else '{}'}")


@router.message(Command("set_privacy"))
async def set_privacy(message: Message, sessionmaker: async_sessionmaker[AsyncSession], client_pool: ClientPool) -> None:
    a = args(message)
    if len(a) != 3:
        await message.answer("用法：/set_privacy <id> <phone|last_seen|profile_photo|forwards|calls|groups> <everybody|contacts|nobody>")
        return
    async with sessionmaker() as session:
        account_id = await resolve_account_id(session, a[0])
        client = await client_pool.get_client(account_id)
        values = await account_ops.set_privacy(client, a[1], a[2])
        await account_ops.save_privacy_snapshot(session, account_id, values)
    await message.answer("隐私设置已更新。")


@router.message(Command("check_2fa"))
async def check_2fa(message: Message, sessionmaker: async_sessionmaker[AsyncSession], client_pool: ClientPool) -> None:
    a = args(message)
    if len(a) != 1:
        await message.answer("用法：/check_2fa <id>")
        return
    async with sessionmaker() as session:
        account_id = await resolve_account_id(session, a[0])
        client = await client_pool.get_client(account_id)
        has_2fa = await account_ops.check_2fa(client)
        await account_ops.update_security_snapshot(session, account_id, has_2fa)
    await message.answer(f"2FA: {'已启用' if has_2fa else '未启用'}")


@router.message(Command("set_2fa", "change_2fa", "disable_2fa"))
async def twofa(message: Message, sessionmaker: async_sessionmaker[AsyncSession], client_pool: ClientPool) -> None:
    command = (message.text or "").split()[0].lstrip("/")
    a = args(message)
    try:
        account_id = int(a[0])
    except Exception:
        await message.answer("用法：/set_2fa <id> <new> [hint] | /change_2fa <id> <old> <new> [hint] | /disable_2fa <id> <old>")
        return
    client = await client_pool.get_client(account_id)
    if command == "set_2fa":
        if len(a) < 2:
            await message.answer("用法：/set_2fa <id> <new_password> [hint]")
            return
        await account_ops.edit_2fa(client, None, a[1], a[2] if len(a) > 2 else None)
        async with sessionmaker() as session:
            await account_ops.update_security_snapshot(session, account_id, True, a[1], a[2] if len(a) > 2 else None)
    elif command == "change_2fa":
        if len(a) < 3:
            await message.answer("用法：/change_2fa <id> <old_password> <new_password> [hint]")
            return
        await account_ops.edit_2fa(client, a[1], a[2], a[3] if len(a) > 3 else None)
        async with sessionmaker() as session:
            await account_ops.update_security_snapshot(session, account_id, True, a[2], a[3] if len(a) > 3 else None)
    else:
        if len(a) != 2:
            await message.answer("用法：/disable_2fa <id> <old_password>")
            return
        await account_ops.edit_2fa(client, a[1], None)
        async with sessionmaker() as session:
            await account_ops.update_security_snapshot(session, account_id, False)
    await message.answer("2FA 操作完成。")


@router.message(Command("spam"))
async def spam(message: Message, sessionmaker: async_sessionmaker[AsyncSession], client_pool: ClientPool) -> None:
    a = args(message)
    if len(a) != 1:
        await message.answer("用法：/spam <id>")
        return
    account_id = int(a[0])
    client = await client_pool.get_client(account_id)
    async with sessionmaker() as session:
        record = await account_ops.spam_check(session, account_id, client)
    await message.answer(f"SpamBot 状态：{account_status_label(record.status_detected)}\n{(record.response_text or '')[:3500]}")


@router.message(Command("spam_all"))
async def spam_all(message: Message, sessionmaker: async_sessionmaker[AsyncSession], client_pool: ClientPool) -> None:
    async with sessionmaker() as session:
        ids = await account_ids_from_range(session, 1, 200)
    ok = 0
    failed = 0
    for account_id in ids:
        try:
            client = await client_pool.get_client(account_id)
            async with sessionmaker() as session:
                await account_ops.spam_check(session, account_id, client)
            ok += 1
        except Exception:
            failed += 1
    await message.answer(f"SpamBot 批量完成：成功 {ok}，失败 {failed}")


@router.message(Command("service_check"))
async def service_check(message: Message, sessionmaker: async_sessionmaker[AsyncSession], client_pool: ClientPool) -> None:
    a = args(message)
    if len(a) != 1:
        await message.answer("用法：/service_check <id>")
        return
    account_id = int(a[0])
    client = await client_pool.get_client(account_id)
    async with sessionmaker() as session:
        inserted = await account_ops.service_check(session, account_id, client)
    await message.answer(f"777000 检查完成，新增 {inserted} 条。")


@router.message(Command("target_allowlist"))
async def target_allowlist(message: Message, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    a = args(message)
    async with sessionmaker() as session:
        if not a or a[0] == "list":
            rows = await session.scalars(select(AllowedTarget).order_by(AllowedTarget.id))
            lines = [f"#{r.id} {r.target_type} {r.target_ref} {r.title or ''}" for r in rows.all()]
            await message.answer("授权目标\n" + ("\n".join(lines) if lines else "暂无"))
            return
        if a[0] == "add" and len(a) >= 3:
            session.add(AllowedTarget(target_type=a[1], target_ref=a[2], title=" ".join(a[3:]) or None))
            await session.commit()
            await message.answer("已添加授权目标。")
            return
        if a[0] == "remove" and len(a) == 2:
            await session.execute(delete(AllowedTarget).where(AllowedTarget.target_ref == a[1]))
            await session.commit()
            await message.answer("已删除授权目标。")
            return
    await message.answer("用法：/target_allowlist add <type> <target> [title] | remove <target> | list")


@router.message(Command("rate"))
async def rate(message: Message, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    a = args(message)
    async with sessionmaker() as session:
        if not a or a[0] == "show":
            rows = await session.scalars(select(RateLimit).order_by(RateLimit.scope))
            lines = [f"{r.scope}: {r.max_actions}/{r.per_seconds}s jitter {r.jitter_min}-{r.jitter_max}s" for r in rows.all()]
            await message.answer("速率配置\n" + ("\n".join(lines) if lines else "暂无"))
            return
        if a[0] == "set" and len(a) == 6:
            row = await session.scalar(select(RateLimit).where(RateLimit.scope == a[1]))
            if not row:
                row = RateLimit(scope=a[1])
                session.add(row)
            row.max_actions = int(a[2])
            row.per_seconds = int(a[3])
            row.jitter_min = int(a[4])
            row.jitter_max = int(a[5])
            await session.commit()
            await message.answer("速率配置已更新。")
            return
    await message.answer("用法：/rate show | /rate set <scope> <max_actions> <per_seconds> <jitter_min> <jitter_max>")


async def run_one_or_many(
    message: Message,
    sessionmaker: async_sessionmaker[AsyncSession],
    admin: Admin | None,
    client_pool: ClientPool,
    job_type: str,
    account_ids: list[int],
    target_ref: str,
    func,
    *op_args,
) -> None:
    async with sessionmaker() as session:
        try:
            await require_allowed_target(session, target_ref)
        except ValueError as exc:
            await message.answer(str(exc), reply_markup=settings_panel())
            return
        rate = await get_rate(session, "batch")
        job = await create_job(session, job_type, {"target": target_ref, "accounts": account_ids})
        await audit(session, admin, job_type, "target", target_ref, {"accounts": account_ids})
        await session.commit()
        job_id = job.id
    gate = RateGate(rate)
    ok = failed = 0
    async with sessionmaker() as session:
        job = await session.get(Job, job_id)
        if job is None:
            await message.answer("任务创建失败。")
            return
        try:
            for account_id in account_ids:
                await gate.wait()
                try:
                    result = await func(client_pool, account_id, target_ref, *op_args)
                    await add_job_item(session, job, account_id, target_ref, "ok", result=result)
                    ok += 1
                except Exception as exc:
                    await add_job_item(session, job, account_id, target_ref, "failed", error=str(exc))
                    failed += 1
                await session.commit()
            await finish_job(session, job, "finished")
        except Exception as exc:
            await session.rollback()
            job = await session.get(Job, job_id)
            if job is not None:
                await finish_job(session, job, "failed", str(exc))
            await message.answer(f"{job_type} 任务失败：{exc}")
            await session.commit()
            return
        await session.commit()
    await message.answer(f"{job_type} 完成：成功 {ok}，失败 {failed}")


@router.message(Command("send", "subscribe", "react", "unreact", "view_post", "forward"))
async def single_batch_command(
    message: Message,
    sessionmaker: async_sessionmaker[AsyncSession],
    admin: Admin | None,
    client_pool: ClientPool,
) -> None:
    command = (message.text or "").split()[0].lstrip("/")
    a = args(message)
    usage = "用法：/send <id> <target> <text> | /subscribe <id> <target> | /react <id> <target> <msg_id> <emoji> | /unreact <id> <target> <msg_id> | /view_post <id> <target> <msg_id> | /forward <id> <source> <msg_id> <target>"
    if len(a) < 2:
        await message.answer(usage)
        return
    async with sessionmaker() as session:
        try:
            account_id = await resolve_account_id(session, a[0])
        except ValueError as exc:
            await message.answer(str(exc))
            return
    if command == "send":
        await run_one_or_many(message, sessionmaker, admin, client_pool, "send", [account_id], a[1], batch_ops.send_message, " ".join(a[2:]))
    elif command == "subscribe":
        await run_one_or_many(message, sessionmaker, admin, client_pool, "subscribe", [account_id], a[1], batch_ops.subscribe)
    elif command == "react":
        await run_one_or_many(message, sessionmaker, admin, client_pool, "react", [account_id], a[1], batch_ops.react, int(a[2]), a[3])
    elif command == "unreact":
        await run_one_or_many(message, sessionmaker, admin, client_pool, "unreact", [account_id], a[1], batch_ops.unreact, int(a[2]))
    elif command == "view_post":
        await run_one_or_many(message, sessionmaker, admin, client_pool, "view_post", [account_id], a[1], batch_ops.view_post, int(a[2]))
    elif command == "forward":
        source, msg_id, target = a[1], int(a[2]), a[3]
        async with sessionmaker() as session:
            await require_allowed_target(session, source)
        await run_one_or_many(message, sessionmaker, admin, client_pool, "forward", [account_id], target, batch_ops.forward, source, msg_id)


@router.message(Command("send_all", "subscribe_all", "react_all", "view_post_all", "forward_all"))
async def many_batch_command(
    message: Message,
    sessionmaker: async_sessionmaker[AsyncSession],
    admin: Admin | None,
    client_pool: ClientPool,
) -> None:
    command = (message.text or "").split()[0].lstrip("/")
    a = args(message)
    if len(a) < 3:
        await message.answer("用法：<cmd> <start_id> <count> <target/source> ...")
        return
    start_id, count = int(a[0]), int(a[1])
    async with sessionmaker() as session:
        account_ids = await account_ids_from_range(session, start_id, count)
    if command == "send_all":
        await run_one_or_many(message, sessionmaker, admin, client_pool, "send_all", account_ids, a[2], batch_ops.send_message, " ".join(a[3:]))
    elif command == "subscribe_all":
        await run_one_or_many(message, sessionmaker, admin, client_pool, "subscribe_all", account_ids, a[2], batch_ops.subscribe)
    elif command == "react_all":
        await run_one_or_many(message, sessionmaker, admin, client_pool, "react_all", account_ids, a[2], batch_ops.react, int(a[3]), a[4])
    elif command == "view_post_all":
        await run_one_or_many(message, sessionmaker, admin, client_pool, "view_post_all", account_ids, a[2], batch_ops.view_post, int(a[3]))
    elif command == "forward_all":
        source, msg_id, target = a[2], int(a[3]), a[4]
        async with sessionmaker() as session:
            await require_allowed_target(session, source)
        await run_one_or_many(message, sessionmaker, admin, client_pool, "forward_all", account_ids, target, batch_ops.forward, source, msg_id)


@router.message(F.text.in_(MENU_TEXTS))
async def menu_text_command(
    message: Message,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
    client_pool: ClientPool,
) -> None:
    action = MENU_TEXTS[message.text or ""]
    if action == "status":
        await message.answer(await status_text(sessionmaker, client_pool), reply_markup=home_panel())
    elif action == "accounts":
        text, accounts_list = await accounts_text_and_rows(sessionmaker)
        await message.answer(text, reply_markup=accounts_panel(accounts_list))
    elif action == "login":
        await login_start(message, state)
    elif action == "import_session":
        await import_session_start(message, state)
    elif action == "export_session":
        await export_session_select(message, state)
    elif action == "batch":
        await message.answer("批量任务入口", reply_markup=batch_panel())
    elif action == "settings":
        await message.answer("目标白名单与速率配置", reply_markup=settings_panel())
    elif action == "monitor":
        await message.answer("监控中心", reply_markup=monitor_panel())
    elif action == "hide":
        await message.answer("已隐藏底部键盘，发送 /start 可重新打开。", reply_markup=remove_keyboard())


@router.callback_query(F.data.startswith("nav:"))
async def nav_callback(
    callback: CallbackQuery,
    sessionmaker: async_sessionmaker[AsyncSession],
    client_pool: ClientPool,
) -> None:
    target = (callback.data or "").split(":", 1)[1]
    if target == "home":
        await answer_panel(callback, "管理入口", home_panel())
    elif target == "status":
        await answer_panel(callback, await status_text(sessionmaker, client_pool), home_panel())
    elif target == "accounts":
        text, accounts_list = await accounts_text_and_rows(sessionmaker)
        await answer_panel(callback, text, accounts_panel(accounts_list))
    elif target == "batch":
        await answer_panel(callback, "批量任务入口", batch_panel())
    elif target == "settings":
        await answer_panel(callback, "目标白名单与速率配置", settings_panel())
    elif target == "monitor":
        await answer_panel(callback, "监控中心", monitor_panel())
    elif target == "help":
        await answer_panel(callback, COMMANDS[:4096], home_panel())


@router.callback_query(F.data.startswith("flow:"))
async def flow_callback(callback: CallbackQuery, state: FSMContext) -> None:
    flow = (callback.data or "").split(":", 1)[1]
    await callback.answer()
    if not callback.message:
        return
    if flow == "login":
        await state.clear()
        await state.set_state(LoginFlow.phone)
        await ask_with_cancel(callback.message, "请输入手机号，格式如 +8613800000000", "+8613800000000")
    elif flow == "import_session":
        await state.clear()
        await state.set_state(ImportSessionFlow.phone)
        await ask_with_cancel(callback.message, "请输入该 session 对应手机号。", "+8613800000000")
    elif flow == "export_session":
        await state.clear()
        await state.set_state(ExportSessionFlow.selection)
        await ask_with_cancel(callback.message, "请输入要导出的账号ID，支持 1,3,5-8。", "1,3,5-8")


@router.callback_query(F.data.startswith("acct:"))
async def account_callback(
    callback: CallbackQuery,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    account_id = int((callback.data or "").split(":", 1)[1])
    async with sessionmaker() as session:
        text = await account_detail_text(session, account_id)
    await answer_panel(callback, text, account_actions_panel(account_id))


@router.callback_query(F.data.startswith("acct_action:"))
async def account_action_callback(
    callback: CallbackQuery,
    sessionmaker: async_sessionmaker[AsyncSession],
    client_pool: ClientPool,
) -> None:
    _, action, account_id_raw = (callback.data or "").split(":", 2)
    account_id = int(account_id_raw)
    await callback.answer("处理中...")
    if not callback.message:
        return
    try:
        if action == "reconnect":
            async with sessionmaker() as session:
                account = await get_account(session, account_id)
                client = await client_pool.get_client(account.id)
                await account_ops.sync_me(session, account, client)
            text = f"重连成功：#{account_id}"
        elif action == "spam":
            client = await client_pool.get_client(account_id)
            async with sessionmaker() as session:
                record = await account_ops.spam_check(session, account_id, client)
            text = f"SpamBot 状态：{account_status_label(record.status_detected)}\n{(record.response_text or '')[:3500]}"
        elif action == "detail":
            client = await client_pool.get_client(account_id)
            live_2fa = await account_ops.get_2fa_info(client)
            async with sessionmaker() as session:
                text = await account_full_detail_text(session, account_id, live_2fa)
        elif action == "check_detail":
            client = await client_pool.get_client(account_id)
            live_2fa = await account_ops.get_2fa_info(client)
            async with sessionmaker() as session:
                await account_ops.spam_check(session, account_id, client)
                text = await account_full_detail_text(session, account_id, live_2fa)
        elif action == "avatar_random":
            client = await client_pool.get_client(account_id)
            text = "随机头像设置失败。"
            last_error = None
            for url in RANDOM_AVATAR_URLS:
                temp_path = Path(tempfile.gettempdir()) / f"tg_random_avatar_{account_id}_{int(datetime.now().timestamp())}.jpg"
                try:
                    await asyncio.to_thread(download_url_to_file, url, temp_path)
                    await account_ops.set_avatar(client, str(temp_path))
                    text = f"随机头像已更新。\n来源：{url}"
                    break
                except Exception as exc:
                    last_error = f"{url}: {type(exc).__name__}: {exc}"
                finally:
                    if temp_path.exists():
                        try:
                            temp_path.unlink()
                        except OSError:
                            pass
            else:
                text = f"随机头像设置失败：{last_error}"
        elif action == "service":
            client = await client_pool.get_client(account_id)
            async with sessionmaker() as session:
                inserted = await account_ops.service_check(session, account_id, client)
            text = f"777000 检查完成，新增 {inserted} 条。"
        elif action == "twofa":
            client = await client_pool.get_client(account_id)
            has_2fa = await account_ops.check_2fa(client)
            async with sessionmaker() as session:
                await account_ops.update_security_snapshot(session, account_id, has_2fa)
            text = f"2FA: {'已启用' if has_2fa else '未启用'}"
        elif action == "privacy":
            async with sessionmaker() as session:
                row = await session.get(PrivacySettings, account_id)
            text = f"隐私快照：{row.rules_json if row else '{}'}"
        elif action == "export_session":
            await send_session_export(callback.message, sessionmaker, [account_id])
            text = "Session 导出完成。"
        else:
            text = "未知账号操作。"
    except Exception as exc:
        text = f"操作失败：{exc}"
    await callback.message.answer(text, reply_markup=account_actions_panel(account_id))


@router.callback_query(F.data.startswith("acct_panel:"))
async def account_panel_callback(callback: CallbackQuery) -> None:
    _, panel, account_id_raw = (callback.data or "").split(":", 2)
    account_id = int(account_id_raw)
    if panel == "profile":
        await answer_panel(callback, "资料设置", profile_edit_panel(account_id))
    elif panel == "avatar":
        await answer_panel(callback, "头像设置", avatar_panel(account_id))
    elif panel == "privacy":
        await answer_panel(callback, "选择要设置的隐私项", privacy_keys_panel(account_id))
    elif panel == "twofa":
        await answer_panel(callback, "2FA 设置", twofa_panel(account_id))
    else:
        await answer_panel(callback, "未知账号面板。", account_actions_panel(account_id))


@router.callback_query(F.data.startswith("acct_edit:"))
async def account_edit_callback(callback: CallbackQuery, state: FSMContext) -> None:
    _, action, account_id_raw = (callback.data or "").split(":", 2)
    account_id = int(account_id_raw)
    prompts = {
        "name": "请输入新姓名，格式：first [last]",
        "bio": "请输入新简介",
        "username": "请输入新用户名，不用带 @",
        "avatar_path": "请输入服务器上的头像图片路径",
        "avatar_upload": "请直接发送一张图片，或以文件形式发送图片。",
    }
    placeholders = {
        "name": "张 三",
        "bio": "账号简介",
        "username": "new_username",
        "avatar_path": "/root/avatar.jpg",
        "avatar_upload": "发送图片",
    }
    await state.clear()
    await state.set_state(ProfileEditFlow.value)
    await state.update_data(account_id=account_id, action=action)
    await ask_callback_with_cancel(callback, prompts.get(action, "请输入新值"), placeholders.get(action, "新值"))


@router.message(ProfileEditFlow.value)
async def profile_edit_value(
    message: Message,
    state: FSMContext,
    bot: Bot,
    sessionmaker: async_sessionmaker[AsyncSession],
    client_pool: ClientPool,
) -> None:
    data = await state.get_data()
    account_id = int(data["account_id"])
    action = data["action"]
    value = (message.text or "").strip()
    client = await client_pool.get_client(account_id)
    temp_path: Path | None = None
    try:
        if action == "name":
            parts = shlex.split(value)
            if not parts:
                await ask_with_cancel(message, "姓名不能为空，请重新输入。", "first [last]")
                return
            async with sessionmaker() as session:
                account = await get_account(session, account_id)
                await account_ops.set_name(client, parts[0], parts[1] if len(parts) > 1 else None)
                await account_ops.sync_me(session, account, client)
            text = "姓名已更新。"
        elif action == "bio":
            await account_ops.set_bio(client, value)
            text = "简介已更新。"
        elif action == "username":
            async with sessionmaker() as session:
                account = await get_account(session, account_id)
                await account_ops.set_username(client, value.lstrip("@"))
                await account_ops.sync_me(session, account, client)
            text = "用户名已更新。"
        elif action == "avatar_path":
            await account_ops.set_avatar(client, value)
            text = "头像已更新。"
        elif action == "avatar_upload":
            source = None
            suffix = ".jpg"
            if message.photo:
                source = message.photo[-1]
            elif message.document and (message.document.mime_type or "").startswith("image/"):
                source = message.document
                if message.document.file_name and "." in message.document.file_name:
                    suffix = "." + message.document.file_name.rsplit(".", 1)[1]
            if source is None:
                await ask_with_cancel(message, "请发送图片，或以文件形式发送图片。", "发送图片")
                return
            with tempfile.NamedTemporaryFile(prefix="tg_avatar_", suffix=suffix, delete=False) as tmp:
                temp_path = Path(tmp.name)
            await bot.download(source, destination=temp_path)
            await account_ops.set_avatar(client, str(temp_path))
            text = "头像已更新。"
        else:
            text = "未知资料操作。"
    except Exception as exc:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass
        await message.answer(f"操作失败：{exc}", reply_markup=profile_edit_panel(account_id))
        return
    await state.clear()
    await message.answer(text, reply_markup=account_actions_panel(account_id))
    if temp_path is not None:
        try:
            temp_path.unlink()
        except OSError:
            pass


@router.callback_query(F.data.startswith("privacy_key:"))
async def privacy_key_callback(callback: CallbackQuery) -> None:
    _, key_name, account_id_raw = (callback.data or "").split(":", 2)
    await answer_panel(callback, f"选择 {key_name} 的可见范围", privacy_rules_panel(int(account_id_raw), key_name))


@router.callback_query(F.data.startswith("privacy_set:"))
async def privacy_set_callback(
    callback: CallbackQuery,
    sessionmaker: async_sessionmaker[AsyncSession],
    client_pool: ClientPool,
) -> None:
    _, key_name, rule_name, account_id_raw = (callback.data or "").split(":", 3)
    account_id = int(account_id_raw)
    await callback.answer("处理中...")
    if not callback.message:
        return
    try:
        client = await client_pool.get_client(account_id)
        values = await account_ops.set_privacy(client, key_name, rule_name)
        async with sessionmaker() as session:
            await account_ops.save_privacy_snapshot(session, account_id, values)
        text = f"隐私设置已更新：{key_name} = {rule_name}"
    except Exception as exc:
        text = f"隐私设置失败：{exc}"
    await callback.message.answer(text, reply_markup=privacy_keys_panel(account_id))


@router.callback_query(F.data.startswith("twofa_edit:"))
async def twofa_edit_callback(callback: CallbackQuery, state: FSMContext) -> None:
    _, action, account_id_raw = (callback.data or "").split(":", 2)
    account_id = int(account_id_raw)
    prompts = {
        "set": "请输入新 2FA 密码，可追加提示和邮箱：new_password [hint] [email]",
        "change": "请输入旧密码和新密码，可追加提示和邮箱：old_password new_password [hint] [email]",
        "email": "配置邮箱需要重新提交当前 2FA 密码。格式：current_password email [hint]",
        "disable": "请输入当前 2FA 密码",
    }
    placeholders = {
        "set": "new_password hint email@example.com",
        "change": "old_password new_password hint email@example.com",
        "email": "current_password email@example.com hint",
        "disable": "current_password",
    }
    await state.clear()
    await state.set_state(TwoFAEditFlow.value)
    await state.update_data(account_id=account_id, action=action)
    await ask_callback_with_cancel(callback, prompts.get(action, "请输入 2FA 参数"), placeholders.get(action, "2FA 参数"))


@router.message(TwoFAEditFlow.value)
async def twofa_edit_value(
    message: Message,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
    client_pool: ClientPool,
) -> None:
    data = await state.get_data()
    account_id = int(data["account_id"])
    action = data["action"]
    try:
        parts = shlex.split(message.text or "")
    except ValueError:
        parts = (message.text or "").split()
    client = await client_pool.get_client(account_id)
    try:
        if action == "set":
            if not parts:
                await ask_with_cancel(message, "请输入新 2FA 密码。", "new_password [hint] [email]")
                return
            hint, email = split_hint_email(parts, 1)
            try:
                await account_ops.edit_2fa(client, None, parts[0], hint, email, require_email_code if email else None)
            except EmailCodeRequired as exc:
                await state.update_data(password=parts[0], hint=hint, email=email)
                await state.set_state(TwoFAEditFlow.email_code)
                await ask_with_cancel(message, f"验证码已发送到邮箱，请输入 {exc.code_length} 位邮箱验证码。", "邮箱验证码")
                return
            async with sessionmaker() as session:
                await account_ops.update_security_snapshot(session, account_id, True, parts[0], hint, email)
            text = "2FA 已设置。"
        elif action == "change":
            if len(parts) < 2:
                await ask_with_cancel(message, "请输入旧密码和新密码。", "old_password new_password [hint] [email]")
                return
            hint, email = split_hint_email(parts, 2)
            try:
                await account_ops.edit_2fa(client, parts[0], parts[1], hint, email, require_email_code if email else None)
            except EmailCodeRequired as exc:
                await state.update_data(password=parts[1], hint=hint, email=email)
                await state.set_state(TwoFAEditFlow.email_code)
                await ask_with_cancel(message, f"验证码已发送到邮箱，请输入 {exc.code_length} 位邮箱验证码。", "邮箱验证码")
                return
            async with sessionmaker() as session:
                await account_ops.update_security_snapshot(session, account_id, True, parts[1], hint, email)
            text = "2FA 已修改。"
        elif action == "email":
            if len(parts) < 2 or "@" not in parts[1]:
                await ask_with_cancel(message, "请输入当前 2FA 密码和邮箱。", "current_password email@example.com [hint]")
                return
            current_password = parts[0]
            email = parts[1]
            hint = " ".join(parts[2:]) or None
            try:
                await account_ops.edit_2fa(
                    client,
                    current_password,
                    current_password,
                    hint,
                    email,
                    require_email_code,
                )
            except EmailCodeRequired as exc:
                await state.update_data(password=current_password, hint=hint, email=email)
                await state.set_state(TwoFAEditFlow.email_code)
                await ask_with_cancel(message, f"验证码已发送到邮箱，请输入 {exc.code_length} 位邮箱验证码。", "邮箱验证码")
                return
            async with sessionmaker() as session:
                await account_ops.update_security_snapshot(session, account_id, True, current_password, hint, email)
            text = "2FA 邮箱已配置。"
        elif action == "disable":
            if len(parts) != 1:
                await ask_with_cancel(message, "请输入当前 2FA 密码。", "current_password")
                return
            await account_ops.edit_2fa(client, parts[0], None)
            async with sessionmaker() as session:
                await account_ops.update_security_snapshot(session, account_id, False)
            text = "2FA 已关闭。"
        else:
            text = "未知 2FA 操作。"
    except PasswordHashInvalidError:
        await message.answer("2FA 密码错误，请重新输入。", reply_markup=twofa_panel(account_id))
        return
    except Exception as exc:
        await message.answer(f"2FA 操作失败：{exc}", reply_markup=twofa_panel(account_id))
        return
    await state.clear()
    await message.answer(text, reply_markup=twofa_panel(account_id))


@router.message(TwoFAEditFlow.email_code)
async def twofa_email_code_value(
    message: Message,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
    client_pool: ClientPool,
) -> None:
    data = await state.get_data()
    account_id = int(data["account_id"])
    code = (message.text or "").strip()
    client = await client_pool.get_client(account_id)
    try:
        await client(functions.account.ConfirmPasswordEmailRequest(code))
        async with sessionmaker() as session:
            await account_ops.update_security_snapshot(
                session,
                account_id,
                True,
                data.get("password"),
                data.get("hint"),
                data.get("email"),
            )
    except Exception as exc:
        await message.answer(f"邮箱验证码确认失败：{exc}", reply_markup=twofa_panel(account_id))
        return
    await state.clear()
    await message.answer("2FA 邮箱已确认并保存。", reply_markup=twofa_panel(account_id))


@router.callback_query(F.data.startswith("settings:"))
async def settings_callback(
    callback: CallbackQuery,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    action = (callback.data or "").split(":", 1)[1]
    async with sessionmaker() as session:
        if action == "targets":
            rows = await session.scalars(select(AllowedTarget).order_by(AllowedTarget.id))
            lines = [f"#{r.id} {r.target_type} {r.target_ref} {r.title or ''}" for r in rows.all()]
            text = "授权目标\n" + ("\n".join(lines) if lines else "暂无")
        elif action == "rate":
            rows = await session.scalars(select(RateLimit).order_by(RateLimit.scope))
            lines = [
                f"{r.scope}: {r.max_actions}/{r.per_seconds}s jitter {r.jitter_min}-{r.jitter_max}s"
                for r in rows.all()
            ]
            text = "速率配置\n" + ("\n".join(lines) if lines else "暂无")
        else:
            text = "未知设置项。"
    await answer_panel(callback, text, settings_panel())


@router.callback_query(F.data.startswith("monitor:"))
async def monitor_callback(callback: CallbackQuery, client_pool: ClientPool) -> None:
    action = (callback.data or "").split(":", 1)[1]
    await callback.answer("处理中...")
    if not callback.message:
        return
    if action == "on":
        await client_pool.connect_all_active()
        text = f"已连接 active 账号：{len(client_pool.clients)}"
    elif action == "off":
        await client_pool.disconnect_all()
        text = "已断开所有实时监听。"
    elif action == "notify":
        text = "通知测试 OK。"
    else:
        text = "未知监控操作。"
    await callback.message.answer(text, reply_markup=monitor_panel())


@router.callback_query(F.data.startswith("template:"))
async def template_callback(callback: CallbackQuery) -> None:
    key = (callback.data or "").split(":", 1)[1]
    template = TEMPLATES.get(key)
    if not template:
        await answer_panel(callback, "未知模板。", home_panel())
        return
    await answer_panel(
        callback,
        f"请按需补全并发送：\n{template}",
        force_reply("补全命令后发送"),
    )


@router.message(Command("notify_test"))
async def notify_test(message: Message) -> None:
    await message.answer("通知测试 OK。")


@router.message(Command("backup"))
async def backup(message: Message) -> None:
    await message.answer(
        "备份建议在 VPS 执行：\n"
        f"mkdir -p {settings.backup_dir}\n"
        f"pg_dump '{settings.sync_database_url}' | gzip > data/backups/tg_account_bot_$(date +%F_%H%M%S).sql.gz\n"
        "注意：数据库内 session/密码字段为加密值，FERNET_KEY 需单独安全保存。"
    )


@router.message(F.text)
async def unknown(message: Message) -> None:
    await message.answer("未知指令，发送 /cmd 查看用法。")
