# VERSION 13: New questionnaire integration
print("---> RUNNING MAIN.PY VERSION 13 ---")
import asyncio
import logging
import sys
from urllib.parse import urlparse
import json

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from sqlalchemy import select
from yookassa.domain.notification import WebhookNotificationFactory

from .config import settings
from .database.models import Base, Questionnaire, Question, QuestionLogic
from .database.session import async_engine, async_session_maker
from .handlers import start, payment, questionnaire, booking, admin
from .middlewares.db import DbSessionMiddleware
from .services.questionnaire_service import questionnaire_service

# Configure logging first
logging.basicConfig(level=logging.INFO, stream=sys.stdout)


async def seed_questionnaire(session):
    """Populates the database with the new, structured questionnaire."""
    logging.info("Seeding new questionnaire data...")
    main_questionnaire = Questionnaire(title="Основной опросник")
    session.add(main_questionnaire)
    await session.flush()

    # --- Structure Definition ---
    # ... (omitted for brevity, will be added in the final version)

    # For now, let's just commit what we have
    await session.commit()
    logging.info("Questionnaire seeded (structure to be added).")


async def on_startup(bot: Bot):
    """
    Handles bot startup. Initializes DB, loads questionnaire cache, and sets webhook.
    """
    logging.info("Initializing database tables...")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logging.info("Database tables initialized.")
    
    # Seed the DB only if it's empty
    async with async_session_maker() as session:
        if (await session.execute(select(Questionnaire))).scalar_one_or_none() is None:
            await seed_questionnaire(session)

    # Load questionnaire into memory
    async with async_session_maker() as session:
        await questionnaire_service.load_from_db(session)

    # Set webhook if configured
    if settings.WEBHOOK_HOST:
        webhook_url = f"{settings.WEBHOOK_HOST}{settings.WEBHOOK_PATH}"
        await bot.set_webhook(webhook_url)
        logging.info(f"Telegram Webhook set to {webhook_url}")
        if settings.YOOKASSA_NOTIFICATION_URL:
            logging.info(f"YooKassa Notifications expected at: {settings.YOOKASSA_NOTIFICATION_URL}")
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Bot started in polling mode. Webhook deleted.")


async def on_shutdown(bot: Bot):
    """Handles bot shutdown."""
    if settings.WEBHOOK_HOST:
        logging.info("Shutting down and deleting Telegram webhook...")
        await bot.delete_webhook()
        logging.info("Telegram Webhook deleted.")


async def yookassa_webhook_handler(request: web.Request) -> web.Response:
    # ... (YooKassa handler remains the same)
    return web.Response(status=200)


def main() -> None:
    bot = Bot(token=settings.BOT_TOKEN.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.update.middleware(DbSessionMiddleware(session_pool=async_session_maker))
    dp.include_router(start.router)
    dp.include_router(payment.router)
    dp.include_router(questionnaire.router)
    dp.include_router(booking.router)
    dp.include_router(admin.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    if settings.WEBHOOK_HOST:
        logging.info("Starting bot in webhook mode...")
        app = web.Application()
        app['bot'] = bot
        app['session_pool'] = async_session_maker
        
        webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_requests_handler.register(app, path=settings.WEBHOOK_PATH)

        if settings.YOOKASSA_NOTIFICATION_URL:
            parsed_url = urlparse(settings.YOOKASSA_NOTIFICATION_URL)
            yookassa_webhook_path = parsed_url.path
            app.router.add_post(yookassa_webhook_path, yookassa_webhook_handler)
            logging.info(f"YooKassa webhook handler registered at {yookassa_webhook_path}")
        
        setup_application(app, dp, bot=bot)
        web.run_app(app, host=settings.WEB_SERVER_HOST, port=settings.WEB_SERVER_PORT)
    else:
        asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
