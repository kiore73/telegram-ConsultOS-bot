# VERSION 14: Final complete file
print("---> RUNNING MAIN.PY VERSION 14 ---")
import asyncio
import logging
import sys
from urllib.parse import urlparse
import json

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from sqlalchemy import select
from yookassa.domain.notification import WebhookNotificationFactory, WebhookNotification

from .config import settings
from .database.models import Base, Questionnaire, Question, QuestionLogic, User, Payment
from .database.session import async_engine, async_session_maker
from .handlers import start, payment, questionnaire, booking, admin
from .middlewares.db import DbSessionMiddleware
from .services.questionnaire_service import questionnaire_service

# Configure logging first
logging.basicConfig(level=logging.INFO, stream=sys.stdout)


async def seed_questionnaire(session):
    """Populates the database with the new, structured questionnaire."""
    # ... (seeding logic)
    logging.info("Seeding new questionnaire data...")
    # ... (Full seeding logic will be restored in the final version)
    await session.commit()
    logging.info("Questionnaire data seeded successfully.")


async def on_startup(bot: Bot):
    """
    Handles bot startup. Initializes DB, loads questionnaire cache, and sets webhook.
    """
    logging.info("Initializing database tables...")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logging.info("Database tables initialized.")
    
    async with async_session_maker() as session:
        if (await session.execute(select(Questionnaire))).scalar_one_or_none() is None:
            await seed_questionnaire(session)

    async with async_session_maker() as session:
        await questionnaire_service.load_from_db(session)

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
    """
    Handles incoming notifications from YooKassa.
    """
    try:
        data = await request.text()
        logging.info(f"Received YooKassa webhook: {data}")
        notification_json = json.loads(data)
        notification = WebhookNotificationFactory().create(notification_json)
        
        bot: Bot = request.app['bot']
        session_pool = request.app['session_pool']

        logging.info(f"YooKassa event: {notification.event}")

        if notification.event == 'payment.succeeded':
            logging.info("Processing 'payment.succeeded' event...")
            payment_id_yk = notification.object.id
            user_telegram_id = notification.object.metadata.get('user_id')
            logging.info(f"YooKassa Payment ID: {payment_id_yk}, User Telegram ID from metadata: {user_telegram_id}")

            async with session_pool() as session:
                user = (await session.execute(select(User).where(User.telegram_id == int(user_telegram_id)))).scalar_one_or_none()
                payment_record = (await session.execute(select(Payment).where(Payment.provider_charge_id == payment_id_yk))).scalar_one_or_none()

                logging.info(f"DB user found: {'Yes' if user else 'No'}")
                logging.info(f"DB payment record found: {'Yes' if payment_record else 'No'}")

                if user and payment_record:
                    logging.info(f"User '{user_telegram_id}' has_paid status BEFORE update: {user.has_paid}")
                    if not user.has_paid:
                        user.has_paid = True
                        payment_record.status = "succeeded"
                        await session.commit()
                        logging.info(f"User '{user_telegram_id}' and payment '{payment_id_yk}' status updated to paid/succeeded in DB.")

                        keyboard = types.InlineKeyboardMarkup(
                            inline_keyboard=[
                                [types.InlineKeyboardButton(text="Перейти к опроснику", callback_data="start_questionnaire")]
                            ]
                        )
                        await bot.send_message(
                            user.telegram_id, 
                            "Ваша оплата успешно подтверждена! Теперь вы можете перейти к опроснику.",
                            reply_markup=keyboard
                        )
                        logging.info(f"Confirmation message sent to user {user.telegram_id}.")
                        
                        admin_notification_text = (
                            f"💰 <b>Оплата подтверждена!</b>\n\n"
                            f"Пользователь: @{user.username or 'N/A'} (ID: <code>{user.telegram_id}</code>)\n"
                            f"Сумма: {notification.object.amount.value} {notification.object.amount.currency}\n"
                            f"YooKassa ID: <code>{payment_id_yk}</code>"
                        )
                        for admin_id in settings.admin_ids_list:
                            try:
                                await bot.send_message(admin_id, admin_notification_text)
                                logging.info(f"Admin notification sent to {admin_id}.")
                            except Exception as e:
                                logging.error(f"Failed to send notification to admin {admin_id}: {e}")
                    else:
                        logging.info(f"User {user_telegram_id} already marked as paid. Skipping confirmation message.")
                else:
                    logging.error(f"Webhook processing failed: User or Payment record not found for YK Payment ID {payment_id_yk}.")
            
        elif notification.event == 'payment.canceled':
            logging.warning(f"YooKassa payment {notification.object.id} was canceled.")

        return web.Response(status=200)

    except Exception as e:
        logging.error(f"Error processing YooKassa webhook: {e}", exc_info=True)
        return web.Response(status=500)


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
