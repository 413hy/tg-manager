from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AllowedTarget


async def is_allowed_target(session: AsyncSession, target_ref: str) -> bool:
    target = await session.scalar(select(AllowedTarget).where(AllowedTarget.target_ref == target_ref))
    return target is not None


async def require_allowed_target(session: AsyncSession, target_ref: str) -> None:
    if not await is_allowed_target(session, target_ref):
        raise ValueError("目标不在授权白名单中，请先使用 /target_allowlist add 添加。")

