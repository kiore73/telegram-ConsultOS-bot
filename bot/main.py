# VERSION 19: Multi-questionnaire logic
print("---> RUNNING MAIN.PY VERSION 19 ---")
import asyncio
import logging
import sys
import time
from urllib.parse import urlparse
import json
from functools import partial

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import joinedload, sessionmaker
from sqlalchemy.ext.asyncio import async_sessionmaker
from yookassa.domain.notification import WebhookNotificationFactory, WebhookNotification
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext

from .config import settings
from .database.models import Base, Questionnaire, Question, QuestionLogic, User, Payment, Tariff
from .database.session import create_session_maker
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


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    logging.info("Starting bot...")

    # Initialize Bot and Dispatcher
    bot = Bot(token=settings.BOT_TOKEN.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Create a fully configured session maker before it's used
    session_maker = await create_session_maker()

    # Register middlewares
    dp.update.middleware(DbSessionMiddleware(session_pool=session_maker))

    # Register handlers
    dp.include_router(start.router)
    dp.include_router(tariff.router)
    dp.include_router(questionnaire.router)
    dp.include_router(booking.router)
    dp.include_router(admin.router)
    dp.include_router(payment_success.router)

    # Initialize database and seed if necessary
    engine = session_maker.kw["bind"]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        result = await conn.execute(select(User).limit(1))
        if result.scalar_one_or_none() is None:
            await seed_database(session_maker)
        else:
            logging.info("Database already contains data, skipping seeding.")

    # Load initial questionnaire cache
    async with session_maker() as session:
        await questionnaire_service.load_from_db(session)
    logging.info("Questionnaire cache loaded.")

    # Decide how to run the bot
    is_webhook_mode = bool(settings.WEBHOOK_HOST and settings.WEBHOOK_HOST.strip())

    if is_webhook_mode:
        await bot.set_webhook(
            url=settings.WEBHOOK_URL,
            drop_pending_updates=True
        )
        logging.info(f"Webhook set to {settings.WEBHOOK_URL}")

        # Webhook handler for YooKassa
        async def yookassa_webhook_handler(request):
            notification_body = await request.json()
            notification = WebhookNotificationFactory().create(notification_body)
            if notification.event == 'payment.succeeded':
                payment_id = notification.object.id
                async with session_maker() as session:
                    result = await session.execute(
                        select(Payment).options(joinedload(Payment.user)).filter_by(yookassa_id=payment_id)
                    )
                    payment = result.scalar_one_or_none()

                    if payment and payment.user:
                        payment.status = 'succeeded'
                        await session.commit()
                        await payment_success.on_payment_success(bot, session, dp, payment)
                    else:
                        logging.warning(f"Payment with yookassa_id {payment_id} or its user not found.")
                return web.Response(status=200)
            return web.Response(status=400)
        
        app = web.Application()
        app.router.add_post(urlparse(settings.WEBHOOK_URL).path, SimpleRequestHandler(dispatcher=dp, bot=bot))
        app.router.add_post("/yookassa_webhook", yookassa_webhook_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host=settings.WEB_SERVER_HOST, port=settings.WEB_SERVER_PORT)
        await site.start()
        
        # Keep the main coroutine running
        await asyncio.Event().wait()

    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Running in long-polling mode.")
        await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped!")
