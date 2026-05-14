from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from app.config import settings
from app.db.models import ServiceMessage, TgSession
from app.services.crypto import decrypt_text

logger = logging.getLogger(__name__)


class ClientPool:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], bot: Bot):
        self.sessionmaker = sessionmaker
        self.bot = bot
        self.clients: dict[int, TelegramClient] = {}
        self._lock = asyncio.Lock()

    async def connect_all_active(self) -> None:
        async with self.sessionmaker() as session:
            rows = await session.scalars(
                select(TgSession.account_id)
                .where(TgSession.is_active.is_(True))
                .order_by(TgSession.account_id)
            )
            for account_id in rows.all():
                try:
                    await self.get_client(account_id)
                except Exception:
                    logger.exception("Failed to connect account %s", account_id)

    async def disconnect_all(self) -> None:
        for client in list(self.clients.values()):
            await client.disconnect()
        self.clients.clear()

    async def drop(self, account_id: int) -> None:
        client = self.clients.pop(account_id, None)
        if client:
            await client.disconnect()

    async def get_client(self, account_id: int) -> TelegramClient:
        async with self._lock:
            existing = self.clients.get(account_id)
            if existing and existing.is_connected():
                return existing
            async with self.sessionmaker() as session:
                tg_session = await session.scalar(
                    select(TgSession)
                    .where(TgSession.account_id == account_id, TgSession.is_active.is_(True))
                    .order_by(TgSession.id.desc())
                )
                if not tg_session:
                    raise ValueError(f"账号 {account_id} 没有可用 session")
                session_str = decrypt_text(tg_session.session_encrypted)
            client = TelegramClient(StringSession(session_str), settings.tg_api_id, settings.tg_api_hash)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                raise ValueError(f"账号 {account_id} session 已失效")
            client.add_event_handler(
                lambda event, aid=account_id: self._handle_777000(aid, event),
                events.NewMessage(from_users=777000),
            )
            self.clients[account_id] = client
            return client

    async def _handle_777000(self, account_id: int, event: events.NewMessage.Event) -> None:
        text = event.raw_text or ""
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        received_at = event.message.date or datetime.now(timezone.utc)
        async with self.sessionmaker() as session:
            exists = await session.scalar(
                select(ServiceMessage).where(
                    ServiceMessage.account_id == account_id,
                    ServiceMessage.message_id == event.message.id,
                )
            )
            if exists:
                return
            record = ServiceMessage(
                account_id=account_id,
                message_id=event.message.id,
                text_hash=text_hash,
                text_preview=text[:1000],
                received_at=received_at,
                notified_at=datetime.now(timezone.utc),
            )
            session.add(record)
            await session.commit()
        for admin_id in settings.admin_ids:
            await self.bot.send_message(
                admin_id,
                f"777000 服务通知\n账号ID: {account_id}\n消息ID: {event.message.id}\n内容:\n{text[:3500]}",
            )
