from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot.handlers import router
from app.config import settings
from app.db.session import init_db, sessionmaker
from app.services.bootstrap import bootstrap_defaults
from app.tg.client_pool import ClientPool
from app.webapp.server import start_webapp


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    settings.session_dir.mkdir(parents=True, exist_ok=True)
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
    await bootstrap_defaults()

    bot = Bot(token=settings.bot_token)
    pool = ClientPool(sessionmaker=sessionmaker, bot=bot)
    dp = Dispatcher(sessionmaker=sessionmaker, client_pool=pool)
    dp.include_router(router)

    web_runner = await start_webapp(sessionmaker, pool)
    if web_runner is not None:
        logging.info("Mini App server started on %s:%s", settings.mini_app_host, settings.mini_app_port)

    await pool.connect_all_active()
    try:
        await dp.start_polling(bot)
    finally:
        if web_runner is not None:
            await web_runner.cleanup()
        await pool.disconnect_all()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
