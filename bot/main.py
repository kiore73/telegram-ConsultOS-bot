import asyncio
import logging
import sys

# Configure logging first
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

import datetime
from .database.models import Base, Questionnaire, Question, QuestionLogic, TimeSlot
from .handlers import start, payment, questionnaire, booking, admin
from .middlewares.db import DbSessionMiddleware
from sqlalchemy import select


async def on_startup():
    """
    Function to be executed on startup.
    It creates all database tables and seeds initial data if necessary.
    """
    logging.info("Bot starting...")
    async with async_engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Seed initial data
    async with async_session_maker() as session:
        # Seed Questionnaire
        result = await session.execute(select(Questionnaire))
        if result.scalar_one_or_none() is None:
            logging.info("Seeding questionnaire data...")
            main_questionnaire = Questionnaire(title="Основной опросник")
            session.add(main_questionnaire)
            await session.flush()
            q1 = Question(questionnaire_id=main_questionnaire.id, text="Какой у вас опыт в IT?", type="single")
            q2 = Question(questionnaire_id=main_questionnaire.id, text="Опишите ваш последний проект.", type="text")
            q3 = Question(questionnaire_id=main_questionnaire.id, text="Какой язык программирования вы предпочитаете?", type="single")
            q4 = Question(questionnaire_id=main_questionnaire.id, text="Спасибо за ваши ответы!", type="text")
            session.add_all([q1, q2, q3, q4])
            await session.flush()
            logic1_1 = QuestionLogic(question_id=q1.id, answer_value="Нет опыта", next_question_id=q2.id)
            logic1_2 = QuestionLogic(question_id=q1.id, answer_value="Меньше года", next_question_id=q3.id)
            logic1_3 = QuestionLogic(question_id=q1.id, answer_value="Больше года", next_question_id=q3.id)
            logic2 = QuestionLogic(question_id=q2.id, answer_value="любой", next_question_id=q4.id)
            logic3 = QuestionLogic(question_id=q3.id, answer_value="любой", next_question_id=q4.id)
            session.add_all([logic1_1, logic1_2, logic1_3, logic2, logic3])
            await session.commit()
            logging.info("Questionnaire data seeded.")

        # Seed TimeSlots
        result = await session.execute(select(TimeSlot))
        if result.scalar_one_or_none() is None:
            logging.info("Seeding time slot data...")
            today = datetime.date.today()
            slots = []
            for day in range(7):  # Seed for the next 7 days
                current_date = today + datetime.timedelta(days=day)
                for hour in range(10, 18, 2): # Slots from 10:00 to 16:00, every 2 hours
                    slots.append(TimeSlot(date=current_date, time=datetime.time(hour, 0), is_available=True))
            session.add_all(slots)
            await session.commit()
            logging.info("Time slot data seeded.")

    logging.info("Database tables checked and seeded if necessary.")


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
    dp.include_router(questionnaire.router)
    dp.include_router(booking.router)
    dp.include_router(admin.router)

    # Start polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
