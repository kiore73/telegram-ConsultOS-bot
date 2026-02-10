import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties

from bot.config import settings
from bot_v2.database import create_db_engine, create_session_maker, Base
from bot_v2.handlers import start
from bot_v2.middlewares.db import DbSessionMiddleware

async def main():
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting bot v2...")

    engine = create_db_engine()
    session_maker = create_session_maker(engine)

    bot = Bot(token=settings.BOT_TOKEN.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Register middleware
    dp.update.middleware(DbSessionMiddleware(session_pool=session_maker))

    # Register handlers
    dp.include_router(start.router)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Running in long-polling mode.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot v2 stopped!")
