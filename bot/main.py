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

import aiofiles

# Import questionnaire data
from .data.basic_questionnaire_data import options_data_basic, question_definitions_basic, logic_rules_definitions_basic
from .data.ayurved_m_questionnaire_data import question_definitions_ayurved_m
from .data.ayurved_j_questionnaire_data import question_definitions_ayurved_j


logging.basicConfig(level=logging.INFO, stream=sys.stdout)


async def _create_questionnaire_from_list(session, title, questions_list):
    """Helper to create a questionnaire and its questions from a list."""
    questionnaire = Questionnaire(title=title)
    session.add(questionnaire)
    await session.flush()

    questions_to_add = []
    logic_to_add = []
    question_map = {}
    prev_question = None

    for q_def in questions_list:
        q = Question(
            questionnaire_id=questionnaire.id,
            text=q_def['text'],
            type=q_def['type'],
            options=q_def.get('options')
        )
        questions_to_add.append(q)
        # We need the ID for linking, so flush after adding all questions for this questionnaire
        # This will get IDs for all questions in questions_to_add
    
    session.add_all(questions_to_add)
    await session.flush() # Get IDs for newly added questions

    # Now that we have IDs, link questions and create logic
    for i, q_def in enumerate(questions_list):
        q = questions_to_add[i] # Get the question with its ID
        question_map[q_def['id']] = q

        if prev_question:
            logic = QuestionLogic(
                question_id=prev_question.id,
                answer_value='любой', 
                next_question_id=q.id
            )
            logic_to_add.append(logic)
        
        prev_question = q
            
    if prev_question:
        final_logic = QuestionLogic(
            question_id=prev_question.id,
            answer_value='любой',
            next_question_id=None
        )
        logic_to_add.append(final_logic)

    session.add_all(logic_to_add)
    # No flush here, let the caller handle commit.

    return questionnaire


async def seed_database(session):
    logging.info("Seeding database with new structure...")

    logging.info("Seeding 'basic' questionnaire...")
    basic_questionnaire = Questionnaire(title="basic")
    session.add(basic_questionnaire)
    await session.flush()

    # Populate basic questionnaire
    question_id_map = {}
    for q_def in question_definitions_basic:
        q_options = options_data_basic.get(q_def['id'])
        question = Question(
            questionnaire_id=basic_questionnaire.id,
            text=q_def['text'],
            type=q_def['type'],
            options=q_options
        )
        session.add(question)
        await session.flush()  # To get the ID for the question
        question_id_map[q_def['id']] = question.id

    for rule_def in logic_rules_definitions_basic:
        logic_rule = QuestionLogic(
            question_id=question_id_map[rule_def['from_id']],
            answer_value=rule_def['answer'],
            next_question_id=question_id_map.get(rule_def['to_id'])
        )
        session.add(logic_rule)
    await session.flush()


    logging.info("Seeding 'ayurved_m' questionnaire...")
    ayurved_m_questionnaire = await _create_questionnaire_from_list(
        session, "ayurved_m", question_definitions_ayurved_m
    )
    logging.info("Seeding 'ayurved_j' questionnaire...")
    ayurved_j_questionnaire = await _create_questionnaire_from_list(
        session, "ayurved_j", question_definitions_ayurved_j
    )

    # Seed initial tariffs
    logging.info("Seeding tariffs...")
    tariffs_to_add = [
        Tariff(title="Базовый", price=2500, description="Базовый тариф"),
        Tariff(title="Сопровождение", price=5000, description="Тариф с сопровождением"),
        Tariff(title="Повторная", price=2000, description="Повторная консультация"),
        Tariff(title="Лайт", price=1500, description="Легкий тариф"),
    ]
    session.add_all(tariffs_to_add)
    await session.flush()

    # Link questionnaires to tariffs
    from sqlalchemy import insert
    tariff_questionnaires_table = Base.metadata.tables['tariff_questionnaires']

    await session.execute(
        insert(tariff_questionnaires_table),
        [
            {"tariff_id": tariffs_to_add[0].id, "questionnaire_id": basic_questionnaire.id},  # Базовый
            {"tariff_id": tariffs_to_add[0].id, "questionnaire_id": ayurved_m_questionnaire.id},
            {"tariff_id": tariffs_to_add[0].id, "questionnaire_id": ayurved_j_questionnaire.id},

            {"tariff_id": tariffs_to_add[1].id, "questionnaire_id": basic_questionnaire.id},  # Сопровождение
            {"tariff_id": tariffs_to_add[1].id, "questionnaire_id": ayurved_m_questionnaire.id},
            {"tariff_id": tariffs_to_add[1].id, "questionnaire_id": ayurved_j_questionnaire.id},

            # Повторная - no questionnaires

            {"tariff_id": tariffs_to_add[3].id, "questionnaire_id": ayurved_m_questionnaire.id},  # Лайт
            {"tariff_id": tariffs_to_add[3].id, "questionnaire_id": ayurved_j_questionnaire.id},
        ],
    )
    await session.commit()
    logging.info("Tariffs and questionnaire links seeded.")


async def on_startup(dispatcher: Dispatcher, bot: Bot):
    await bot.set_webhook(url=settings.WEBHOOK_URL)
    logging.info("Webhook set up.")

    # Initialize database engine and create tables
    engine = init_engine()
    async with engine.begin() as conn:
        # Create tables
        await conn.run_sync(Base.metadata.create_all)

        # Check if database is empty and seed if necessary
        result = await conn.execute(select(User).limit(1))
        if result.scalar_one_or_none() is None:
            await seed_database(async_session_maker)
        else:
            logging.info("Database already contains data, skipping seeding.")

    # Load initial questionnaire cache
    async with async_session_maker() as session:
        await questionnaire_service.load_from_db(session)
    logging.info("Questionnaire cache loaded.")

    # Register admin commands
    from .handlers.admin import register_admin_handlers
    register_admin_handlers(dispatcher.router)


def main():
    logging.info("Starting bot...")
    bot = Bot(token=settings.BOT_TOKEN.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher(storage=MemoryStorage())

    # Register middlewares
    dispatcher.message.middleware(DbSessionMiddleware(async_session_maker))
    dispatcher.callback_query.middleware(DbSessionMiddleware(async_session_maker))

    # Register handlers
    dispatcher.include_router(start.router)
    dispatcher.include_router(tariff.router)
    dispatcher.include_router(questionnaire.router)
    dispatcher.include_router(booking.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(payment_success.router)


    # Webhook handler for YooKassa
    async def yookassa_webhook_handler(request):
        notification_body = await request.json()
        notification = WebhookNotificationFactory().create(notification_body)
        if notification.event == 'payment.succeeded':
            payment_id = notification.object.id
            async with async_session_maker() as session:
                async with session.begin():
                    payment = await session.execute(select(Payment).filter_by(yookassa_id=payment_id))
                    payment = payment.scalar_one_or_none()
                    if payment:
                        payment.status = 'succeeded'
                        # Trigger the payment success logic
                        await payment_success.on_payment_success(payment, bot, session)
                    else:
                        logging.warning(f"Payment with yookassa_id {payment_id} not found.")
            return web.Response(status=200)
        return web.Response(status=400)


    # Start long-polling or webhook
    if settings.WEBHOOK_HOST:
        app = web.Application()
        app.router.add_post("/webhook", SimpleRequestHandler(dispatcher, bot, process_update=True))
        app.router.add_post("/yookassa_webhook", yookassa_webhook_handler)
        setup_application(app, dispatcher, bot=bot)
        web.run_app(app, host="0.0.0.0", port=settings.WEBHOOK_PORT)
    else:
        # Long-polling setup
        async def start_polling():
            await on_startup(dispatcher, bot)  # Manually call on_startup for long-polling
            await dispatcher.start_polling(bot)

        asyncio.run(start_polling())
    logging.info("Bot stopped.")


if __name__ == "__main__":
    main()

