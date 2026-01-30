import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from .config import settings
from .database.session import async_engine, async_session_maker
from .database.models import Base
from .handlers import start, payment
from .middlewares.db import DbSessionMiddleware


async def on_startup():
    """
    Function to be executed on startup.
    It creates all database tables.
    """
    logging.info("Bot starting...")
    async with async_engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Use for dropping tables
        await conn.run_sync(Base.metadata.create_all)
    logging.info("Database tables created.")


async def main() -> None:
    # Initialize Bot instance with a default parse mode which will be passed to all API calls
    bot = Bot(settings.BOT_TOKEN.get_secret_value(), parse_mode=ParseMode.HTML)
    
    # Create a dispatcher
    dp = Dispatcher()

    # Register middleware
    dp.update.middleware(DbSessionMiddleware(session_pool=async_session_maker))

    # Register startup function
    dp.startup.register(on_startup)

    # Register routers
    dp.include_router(start.router)
    dp.include_router(payment.router)

    # Start polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
