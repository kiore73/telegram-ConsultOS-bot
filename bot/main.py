# VERSION 19: Multi-questionnaire logic
print("---> RUNNING MAIN.PY VERSION 19 ---")
import asyncio
import logging
import sys
import time
from urllib.parse import urlparse
import json

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from yookassa.domain.notification import WebhookNotificationFactory, WebhookNotification
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext

from .config import settings
from .database.models import Base, Questionnaire, Question, QuestionLogic, User, Payment, Tariff
from .database.session import init_engine, async_session_maker
from .handlers import start, tariff, questionnaire, booking, admin, payment_success
from .middlewares.db import DbSessionMiddleware
from .services.questionnaire_service import questionnaire_service

logging.basicConfig(level=logging.INFO, stream=sys.stdout)


async def _create_questionnaire_from_list(session, title, questions_list):
    """Helper to create a questionnaire and its questions from a list."""
    questionnaire = Questionnaire(title=title)
    session.add(questionnaire)
    await session.flush()

    question_map = {}
    prev_question_id = None

    for i, q_def in enumerate(questions_list):
        q = Question(
            questionnaire_id=questionnaire.id,
            text=q_def['text'],
            type=q_def['type'],
            options=q_def.get('options')
        )
        session.add(q)
        await session.flush()
        question_map[q_def['id']] = q

        if prev_question_id:
            logic = QuestionLogic(
                question_id=prev_question_id,
                answer_value='любой', 
                next_question_id=q.id
            )
            session.add(logic)
        
        prev_question_id = q.id
            
    if prev_question_id:
        final_logic = QuestionLogic(
            question_id=prev_question_id,
            answer_value='любой',
            next_question_id=None
        )
        session.add(final_logic)

    return questionnaire


async def seed_database(session):
    logging.info("Seeding database with new structure...")

    logging.info("Seeding 'basic' questionnaire...")
    basic_questionnaire = Questionnaire(title="basic")
    session.add(basic_questionnaire)
    await session.flush()
    q_gender = Question(questionnaire_id=basic_questionnaire.id, text="Укажите ваш пол", type='single', options=['Мужчина', 'Женщина'])
    session.add(q_gender)

    logging.info("Seeding 'ayurved_m' questionnaire...")
    with open('аюрвед_м.txt', 'r', encoding='utf-8') as f:
        ayurved_m_questions = json.load(f)
    ayurved_m_questionnaire = await _create_questionnaire_from_list(session, 'ayurved_m', ayurved_m_questions)

    logging.info("Seeding 'ayurved_j' questionnaire...")
    with open('аюрвед_ж.txt', 'r', encoding='utf-8') as f:
        ayurved_j_questions = json.load(f)
    ayurved_j_questionnaire = await _create_questionnaire_from_list(session, 'ayurved_j', ayurved_j_questions)

    await session.flush()

    logging.info("Seeding tariffs...")
    tariffs_data = {
        'Базовый': {'price': 1000, 'description': 'Полная консультация'},
        'Сопровождение': {'price': 2000, 'description': 'Полная консультация с сопровождением'},
        'Повторная': {'price': 500, 'description': 'Повторная консультация'},
        'Лайт': {'price': 300, 'description': 'Экспресс-консультация'},
    }
    tariffs = {}
    for name, data in tariffs_data.items():
        tariff = Tariff(name=name, price=data['price'], description=data['description'])
        session.add(tariff)
        tariffs[name] = tariff
    await session.flush()

    logging.info("Linking tariffs to questionnaires...")
    tariffs['Базовый'].questionnaires.extend([basic_questionnaire, ayurved_m_questionnaire, ayurved_j_questionnaire])
    tariffs['Сопровождение'].questionnaires.extend([basic_questionnaire, ayurved_m_questionnaire, ayurved_j_questionnaire])
    tariffs['Лайт'].questionnaires.extend([ayurved_m_questionnaire, ayurved_j_questionnaire])
    
    await session.commit()
    logging.info("Database seeding completed successfully.")


async def on_startup(bot: Bot):
    startup_start_time = time.time()
    logging.info("--- Bot Starting Up ---")

    db_init_start = time.time()
    logging.info("Step 1: Initializing database tables...")
    from .database.session import async_engine
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logging.info(f"Step 1: Database tables initialized. (Took {time.time() - db_init_start:.4f}s)")

    seed_start = time.time()
    logging.info("Step 2: Checking if database needs to be seeded...")
    async with async_session_maker() as session:
        result = await session.execute(select(Tariff).limit(1))
        if not result.scalar_one_or_none():
            logging.info("No tariffs found. Seeding database...")
            await seed_database(session)
        else:
            logging.info(f"Step 2: Database already seeded. Skipping. (Took {time.time() - seed_start:.4f}s)")

    cache_load_start = time.time()
    logging.info("Step 3: Loading questionnaire cache from database...")
    async with async_session_maker() as session:
        await questionnaire_service.load_from_db(session)
    logging.info(f"Step 3: Questionnaire cache loaded. (Took {time.time() - cache_load_start:.4f}s)")

    webhook_setup_start = time.time()
    logging.info("Step 4: Configuring Telegram webhook...")
    if settings.WEBHOOK_HOST:
        webhook_url = f"{settings.WEBHOOK_HOST}{settings.WEBHOOK_PATH}"
        await bot.set_webhook(webhook_url)
        logging.info(f"Telegram Webhook set to {webhook_url}")
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Bot started in polling mode. Webhook deleted.")
    logging.info(f"Step 4: Webhook configured. (Took {time.time() - webhook_setup_start:.4f}s)")
    
    logging.info(f"--- Bot Startup Complete. Total time: {time.time() - startup_start_time:.4f}s ---")


async def on_shutdown(bot: Bot):
    if settings.WEBHOOK_HOST:
        logging.info("Shutting down and deleting Telegram webhook...")
        await bot.delete_webhook()
        logging.info("Telegram Webhook deleted.")


async def yookassa_webhook_handler(request: web.Request) -> web.Response:
    try:
        data = await request.text()
        notification_json = json.loads(data)
        notification = WebhookNotificationFactory().create(notification_json)
        
        bot: Bot = request.app['bot']
        dp: Dispatcher = request.app['dp']
        session_pool = request.app['session_pool']

        if notification.event == 'payment.succeeded':
            metadata = notification.object.metadata
            user_telegram_id = int(metadata.get('user_id'))
            
            async with session_pool() as session:
                user_result = await session.execute(
                    select(User).options(joinedload(User.tariff)).where(User.telegram_id == user_telegram_id)
                )
                user = user_result.scalar_one_or_none()
                
                if user and not user.has_paid:
                    user.has_paid = True
                    await session.commit()
                    
                    storage = dp.storage if dp.storage else MemoryStorage()
                    state = FSMContext(storage, key=str(user_telegram_id))

                    await payment_success.on_payment_success(bot, session, state, user)

                    admin_notification_text = (
                        f"💰 Оплата!\n"
                        f"User: @{user.username or 'N/A'} (ID: {user.telegram_id})\n"
                        f"Tariff: {user.tariff.name if user.tariff else 'N/A'}"
                    )
                    for admin_id in settings.admin_ids_list:
                        await bot.send_message(admin_id, admin_notification_text)
            
        return web.Response(status=200)

    except Exception as e:
        logging.error(f"Error processing YooKassa webhook: {e}", exc_info=True)
        return web.Response(status=500)


def main() -> None:
    init_engine()
    bot = Bot(token=settings.BOT_TOKEN.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.update.middleware(DbSessionMiddleware(session_pool=async_session_maker))
    dp.include_router(start.router)
    dp.include_router(tariff.router)
    dp.include_router(questionnaire.router)
    dp.include_router(booking.router)
    dp.include_router(admin.router)
    dp.include_router(payment_success.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    if settings.WEBHOOK_HOST:
        app = web.Application()
        app['bot'] = bot
        app['dp'] = dp
        app['session_pool'] = async_session_maker
        
        webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_requests_handler.register(app, path=settings.WEBHOOK_PATH)

        if settings.YOOKASSA_NOTIFICATION_URL:
            parsed_url = urlparse(settings.YOOKASSA_NOTIFICATION_URL)
            yookassa_webhook_path = parsed_url.path
            app.router.add_post(yookassa_webhook_path, yookassa_webhook_handler)
        
        setup_application(app, dp, bot=bot)
        web.run_app(app, host=settings.WEB_SERVER_HOST, port=settings.WEB_SERVER_PORT)
    else:
        asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)
        time.sleep(5)
        sys.exit(1)
