import asyncio
import logging
import sys
import datetime

# Configure logging first
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from sqlalchemy import select

from .config import settings
from .database.models import Base, Questionnaire, Question, QuestionLogic, TimeSlot
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

        if (await session.execute(select(TimeSlot))).scalar_one_or_none() is None:
            logging.info("Seeding time slot data...")
            today = datetime.date.today()
            slots = []
            for day in range(7):
                current_date = today + datetime.timedelta(days=day)
                for hour in range(10, 18, 2):
                    slots.append(TimeSlot(date=current_date, time=datetime.time(hour, 0), is_available=True))
            session.add_all(slots)
            await session.commit()
            logging.info("Time slot data seeded.")
    logging.info("Database initialization complete.")


async def on_startup_webhook(bot: Bot):
    await init_db()
    webhook_url = f"{settings.WEBHOOK_HOST}{settings.WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)
    logging.info(f"Webhook set to {webhook_url}")


async def on_shutdown_webhook(bot: Bot):
    logging.info("Shutting down and deleting webhook...")
    await bot.delete_webhook()
    logging.info("Webhook deleted.")


async def start_polling(dp: Dispatcher, bot: Bot):
    logging.info("Starting bot in polling mode...")
    dp.startup.register(init_db)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


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
        webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_requests_handler.register(app, path=settings.WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        
        web.run_app(app, host=settings.WEB_SERVER_HOST, port=settings.WEB_SERVER_PORT)
    else:
        asyncio.run(start_polling(dp, bot))


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
