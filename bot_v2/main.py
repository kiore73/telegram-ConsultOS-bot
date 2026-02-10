import asyncio
import logging
from urllib.parse import urlparse
import json

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from sqlalchemy import select, insert
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import settings
from bot_v2.database import create_db_engine, create_session_maker, Base
from bot_v2.database.models import User, Tariff, Questionnaire, Question, QuestionLogic, Payment
from bot_v2.handlers import start, tariff # Import tariff router
from bot_v2.middlewares.db import DbSessionMiddleware

# Import questionnaire data
from bot.data.basic_questionnaire_data import options_data_basic, question_definitions_basic, logic_rules_definitions_basic
from bot.data.ayurved_m_questionnaire_data import question_definitions_ayurved_m
from bot.data.ayurved_j_questionnaire_data import question_definitions_ayurved_j

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
    logging.info("Starting bot v2...")

    engine = create_db_engine()
    session_maker = create_session_maker(engine)

    bot = Bot(token=settings.BOT_TOKEN.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.update.middleware(DbSessionMiddleware(session_pool=session_maker))

    dp.include_router(start.router)
    dp.include_router(tariff.router) # Include the tariff router

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        result = await conn.execute(select(User).limit(1))
        if result.scalar_one_or_none() is None:
            await seed_database(session_maker)
        else:
            logging.info("Database already contains data, skipping seeding.")

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Running in long-polling mode.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot v2 stopped!")
