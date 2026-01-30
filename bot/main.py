import asyncio
import logging
import sys
import datetime
import json

# Configure logging first
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from aiogram import Bot, Dispatcher, types # Added types here
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from sqlalchemy import select
from yookassa.domain.notification import WebhookNotificationFactory, WebhookNotification

from .config import settings
from .database.models import Base, Questionnaire, Question, QuestionLogic, TimeSlot, User, Payment
from .database.session import async_engine, async_session_maker
from .handlers import start, payment, questionnaire, booking, admin
from .middlewares.db import DbSessionMiddleware


async def init_db():
    """ Initializes the database and seeds initial data if necessary. """
    logging.info("Initializing database...")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        # Seed data logic...
        if (await session.execute(select(Questionnaire))).scalar_one_or_none() is None:
            logging.info("Seeding questionnaire data...")
            main_questionnaire = Questionnaire(title="Основной опросник")
            session.add(main_questionnaire)
            await session.flush()
            q1 = Question(questionnaire_id=main_questionnaire.id, text="Какой у вас опыт в IT?", type="single")
            q2 = Question(questionnaire_id=main_questionnaire.id, text="Опишите ваш последний проект.", type="text")
            q3 = Question(questionnaire_id=main_questionnaire.id, text="Какие технологии вы использовали?", type="multi")
            q4 = Question(questionnaire_id=main_questionnaire.id, text="Приложите скриншот вашей последней работы (необязательно)", type="photo")
            q5 = Question(questionnaire_id=main_questionnaire.id, text="Спасибо за ваши ответы!", type="text")
            session.add_all([q1, q2, q3, q4, q5])
            await session.flush()
            logic1_1 = QuestionLogic(question_id=q1.id, answer_value="Нет опыта", next_question_id=q2.id)
            logic1_2 = QuestionLogic(question_id=q1.id, answer_value="Меньше года", next_question_id=q3.id)
            logic1_3 = QuestionLogic(question_id=q1.id, answer_value="Больше года", next_question_id=q3.id)
            logic2 = QuestionLogic(question_id=q2.id, answer_value="любой", next_question_id=q5.id)
            logic3_1 = QuestionLogic(question_id=q3.id, answer_value="Python", next_question_id=None)
            logic3_2 = QuestionLogic(question_id=q3.id, answer_value="JavaScript", next_question_id=None)
            logic3_3 = QuestionLogic(question_id=q3.id, answer_value="SQL", next_question_id=None)
            logic3_4 = QuestionLogic(question_id=q3.id, answer_value="Docker", next_question_id=None)
            logic3_any = QuestionLogic(question_id=q3.id, answer_value="любой", next_question_id=q4.id)
            logic4_any = QuestionLogic(question_id=q4.id, answer_value="любой", next_question_id=q5.id)
            session.add_all([logic1_1, logic1_2, logic1_3, logic2, logic3_1, logic3_2, logic3_3, logic3_4, logic3_any, logic4_any])
            await session.commit()
            logging.info("Questionnaire data seeded.")

    logging.info("Database initialization complete.")


async def on_startup_webhook(bot: Bot):
    await init_db()
    webhook_url = f"{settings.WEBHOOK_HOST}{settings.WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)
    logging.info(f"Telegram Webhook set to {webhook_url}")

    if settings.YOOKASSA_NOTIFICATION_URL:
        # We need to explicitly set the webhook URL for YooKassa
        # However, this is done by setting Configuration.webhook_url in YooKassaService __init__
        # So we just log it here.
        logging.info(f"YooKassa Notifications expected at: {settings.YOOKASSA_NOTIFICATION_URL}")


async def on_shutdown_webhook(bot: Bot):
    logging.info("Shutting down and deleting Telegram webhook...")
    await bot.delete_webhook()
    logging.info("Telegram Webhook deleted.")


async def start_polling(dp: Dispatcher, bot: Bot):
    logging.info("Starting bot in polling mode...")
    dp.startup.register(init_db)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


async def yookassa_webhook_handler(request: web.Request) -> web.Response:
    """
    Handles incoming notifications from YooKassa.
    """
    try:
        data = await request.text()
        notification = WebhookNotificationFactory().create(json.loads(data))
        
        bot: Bot = request.app['bot']
        session_pool = request.app['session_pool']

        if notification.event == 'payment.succeeded':
            payment_id_yk = notification.object.id
            user_telegram_id = notification.object.metadata.get('user_id')

            async with session_pool() as session:
                user = (await session.execute(select(User).where(User.telegram_id == int(user_telegram_id)))).scalar_one_or_none()
                payment = (await session.execute(select(Payment).where(Payment.provider_charge_id == payment_id_yk))).scalar_one_or_none()

                if user and payment:
                    if not user.has_paid: # Only update if not already paid
                        user.has_paid = True
                        payment.status = "success"
                        await session.commit()

                        # Notify user with a button to start the questionnaire
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
                        
                        # Notify admins
                        admin_notification_text = (
                            f"💰 \u003cb\u003eНОВОЕ УВЕДОМЛЕНИЕ ОТ ЮKASSA: Оплата подтверждена!\u003c/b\u003e\n\n"
                            f"Пользователь: {user.username or 'N/A'} (ID: \u003ccode\u003e{user.telegram_id}\u003c/code\u003e)\n"
                            f"Сумма: {notification.object.amount.value} {notification.object.amount.currency}\n"
                            f"YooKassa Payment ID: \u003ccode\u003e{payment_id_yk}\u003c/code\u003e"
                        )
                        for admin_id in settings.admin_ids_list:
                            try:
                                await bot.send_message(admin_id, admin_notification_text)
                            except Exception as e:
                                logging.error(f"Failed to send YK notification to admin {admin_id}: {e}")
                    else:
                        logging.info(f"YooKassa notification received for already paid user {user_telegram_id}, payment {payment_id_yk}. Skipping.")
                else:
                    logging.error(f"YooKassa notification for payment {payment_id_yk}: User or Payment record not found in DB. User ID: {user_telegram_id}")
            
        elif notification.event == 'payment.canceled' or notification.event == 'payment.failed':
            # Handle canceled/failed payments (e.g., update DB status, notify)
            logging.warning(f"YooKassa payment {notification.object.id} {notification.event}.")
            # TODO: Implement full handling for canceled/failed payments

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

    if settings.WEBHOOK_HOST:
        logging.info("Starting bot in webhook mode...")
        dp.startup.register(on_startup_webhook)
        dp.shutdown.register(on_shutdown_webhook)
        
        app = web.Application()
        app['bot'] = bot # Make bot accessible in webhook handler
        app['session_pool'] = async_session_maker # Make session pool accessible
        
        # Register Telegram webhook handler
        webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_requests_handler.register(app, path=settings.WEBHOOK_PATH)

        # Register YooKassa webhook handler
        if settings.YOOKASSA_NOTIFICATION_URL:
            # The path needs to be extracted from the full URL for aiohttp routing
            from urllib.parse import urlparse
            parsed_url = urlparse(settings.YOOKASSA_NOTIFICATION_URL)
            yookassa_webhook_path = parsed_url.path
            app.router.add_post(yookassa_webhook_path, yookassa_webhook_handler)
            logging.info(f"YooKassa webhook handler registered at {yookassa_webhook_path}")
        
        setup_application(app, dp, bot=bot)
        
        web.run_app(app, host=settings.WEB_SERVER_HOST, port=settings.WEB_SERVER_PORT)
    else:
        asyncio.run(start_polling(dp, bot))


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
