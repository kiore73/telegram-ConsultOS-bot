# VERSION 20: Definitive Fix
print("---> RUNNING MAIN.PY VERSION 20 ---")
import asyncio
import logging
from urllib.parse import urlparse
import json

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import async_sessionmaker
from yookassa.domain.notification import WebhookNotificationFactory, WebhookNotification
from aiogram.fsm.storage.memory import MemoryStorage

from .config import settings
from .database.models import Base, Questionnaire, Question, QuestionLogic, User, Payment, Tariff
from .database.session import create_session_maker
from .handlers import start, tariff, questionnaire, booking, admin, payment_success
from .middlewares.db import DbSessionMiddleware
from .services.questionnaire_service import questionnaire_service

# Import questionnaire data
from .data.basic_questionnaire_data import options_data_basic, question_definitions_basic, logic_rules_definitions_basic
from .data.ayurved_m_questionnaire_data import question_definitions_ayurved_m
from .data.ayurved_j_questionnaire_data import question_definitions_ayurved_j


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
    
    session.add_all(questions_to_add)
    await session.flush()

    for i, q_def in enumerate(questions_list):
        q = questions_to_add[i]
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
    return questionnaire


async def seed_database(session_maker: async_sessionmaker):
    logging.info("Seeding database with new structure...")
    async with session_maker() as session:
        logging.info("Seeding 'basic' questionnaire...")
        basic_questionnaire = Questionnaire(title="basic")
        session.add(basic_questionnaire)
        await session.flush()

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
            await session.flush()
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

        logging.info("Seeding tariffs...")
        tariffs_to_add = [
            Tariff(title="Базовый", price=2500, description="Базовый тариф"),
            Tariff(title="Сопровождение", price=5000, description="Тариф с сопровождением"),
            Tariff(title="Повторная", price=2000, description="Повторная консультация"),
            Tariff(title="Лайт", price=1500, description="Легкий тариф"),
        ]
        session.add_all(tariffs_to_add)
        await session.flush()

        from sqlalchemy import insert
        tariff_questionnaires_table = Base.metadata.tables['tariff_questionnaires']
        await session.execute(
            insert(tariff_questionnaires_table),
            [
                {"tariff_id": tariffs_to_add[0].id, "questionnaire_id": basic_questionnaire.id},
                {"tariff_id": tariffs_to_add[0].id, "questionnaire_id": ayurved_m_questionnaire.id},
                {"tariff_id": tariffs_to_add[0].id, "questionnaire_id": ayurved_j_questionnaire.id},
                {"tariff_id": tariffs_to_add[1].id, "questionnaire_id": basic_questionnaire.id},
                {"tariff_id": tariffs_to_add[1].id, "questionnaire_id": ayurved_m_questionnaire.id},
                {"tariff_id": tariffs_to_add[1].id, "questionnaire_id": ayurved_j_questionnaire.id},
                {"tariff_id": tariffs_to_add[3].id, "questionnaire_id": ayurved_m_questionnaire.id},
                {"tariff_id": tariffs_to_add[3].id, "questionnaire_id": ayurved_j_questionnaire.id},
            ],
        )
        await session.commit()
        logging.info("Tariffs and questionnaire links seeded.")


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    logging.info("Starting bot...")

    bot = Bot(token=settings.BOT_TOKEN.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    
    session_maker = await create_session_maker()

    dp.update.middleware(DbSessionMiddleware(session_pool=session_maker))

    dp.include_router(start.router)
    dp.include_router(tariff.router)
    dp.include_router(questionnaire.router)
    dp.include_router(booking.router)
    dp.include_router(admin.router)
    dp.include_router(payment_success.router)

    engine = session_maker.kw["bind"]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        result = await conn.execute(select(User).limit(1))
        if result.scalar_one_or_none() is None:
            await seed_database(session_maker)
        else:
            logging.info("Database already contains data, skipping seeding.")

    async with session_maker() as session:
        await questionnaire_service.load_from_db(session)
    logging.info("Questionnaire cache loaded.")

    is_webhook_mode = bool(settings.WEBHOOK_HOST and settings.WEBHOOK_HOST.strip())

    if is_webhook_mode:
        await bot.set_webhook(
            url=settings.WEBHOOK_URL,
            drop_pending_updates=True
        )
        logging.info(f"Webhook set to {settings.WEBHOOK_URL}")

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