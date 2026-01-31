print("---> RUNNING MAIN.PY VERSION 4 ---")
import asyncio
import logging
import sys
import datetime
import json
from urllib.parse import urlparse

# Configure logging first
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from aiogram import Bot, Dispatcher, types
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
        if (await session.execute(select(Questionnaire))).scalar_one_or_none() is None:
            logging.info("Seeding new questionnaire data...")
            main_questionnaire = Questionnaire(title="Основной опросник")
            session.add(main_questionnaire)
            await session.flush()

            # --- Define all questions ---
            question_definitions = [
                {'str_id': 'gender_selection', 'text': 'Пожалуйста, укажите ваш пол:', 'type': 'single', 'options': ['Мужской', 'Женский']},
                # GENERAL BLOCK
                {'str_id': 'general_01', 'text': 'Ваш род занятий, работа', 'type': 'multi', 'options': ['сидячая', 'присутствует физическая нагрузка', 'высокая умственная нагрузка / высокий уровень ответственности', 'приходится долго стоять', 'много разъездов, поездок, перелетов']},
                {'str_id': 'general_02', 'text': 'Присутствуют ли в вашей жизни спорт и физическая активность?', 'type': 'single', 'options': ['да, регулярно', 'нерегулярно, время от времени', 'нет и не было', 'я профессиональный спортсмен']},
                {'str_id': 'general_03', 'text': 'Если у вас есть или были хронические / наследственные заболевания — укажите какие', 'type': 'text'},
                {'str_id': 'general_04', 'text': 'Есть ли хронические / генетические заболевания у ваших близких родственников?', 'type': 'text'},
                {'str_id': 'general_05', 'text': 'Были ли у вас операции? Какие и как давно?', 'type': 'text'},
                {'str_id': 'general_06', 'text': 'Принимаете ли вы на постоянной основе фармпрепараты или БАДы? Если да — какие', 'type': 'text'},
                {'str_id': 'general_07', 'text': 'Испытываете ли вы симптомы аллергии?', 'type': 'single', 'options': ['очень часто', 'иногда', 'сезонно', 'нет']},
                {'str_id': 'general_08', 'text': 'Как часто вы переносите сезонные ОРВИ?', 'type': 'single', 'options': ['очень редко', '1–2 раза в год', '3–4 раза в год', 'постоянно, даже летом']},
                {'str_id': 'general_09', 'text': 'Кратко опишите ваш режим дня (сон, работа, питание, транспорт, прогулки, хобби)', 'type': 'text'},
                {'str_id': 'general_10', 'text': 'Оцените качество вашего сна', 'type': 'multi', 'options': ['быстро засыпаю', 'засыпаю более 40 минут', 'сон крепкий, без пробуждений', 'есть пробуждения ночью', 'есть трекер сна, могу прикрепить отчет', 'просыпаюсь легко и чувствую восстановление', 'сложно проснуться, но потом бодр', 'тяжело просыпаюсь, нет сил до обеда']},
                {'str_id': 'general_11', 'text': 'Знакомы ли вы с правилами гигиены сна?', 'type': 'single', 'options': ['да, стараюсь придерживаться', 'да, но не получается соблюдать', 'нет, не знаком']},
                {'str_id': 'general_12', 'text': 'Бывают ли у вас мышечные судороги, спазмы, онемение?', 'type': 'multi', 'options': ['нет', 'ночные судороги ног', 'спазмы мышц шеи', 'регулярные судороги', 'онемение конечностей']},
                {'str_id': 'general_13', 'text': 'Испытываете ли вы головокружение?', 'type': 'single', 'options': ['да, часто', 'иногда', 'нет']},
                {'str_id': 'general_14', 'text': 'Знаете ли вы своё артериальное давление и пульс?', 'type': 'single', 'options': ['не знаю', 'повышенное / гипертония', 'пониженное', 'нестабильное', 'есть трекер']},
                {'str_id': 'general_15', 'text': 'Беспокоят ли вас отеки?', 'type': 'multi', 'options': ['нет', 'постоянно', 'летом', 'ноги', 'лицо и руки']},
                {'str_id': 'general_16', 'text': 'Бывают ли частые или ночные позывы к мочеиспусканию?', 'type': 'single', 'options': ['да', 'иногда', 'нет']},
                {'str_id': 'general_17', 'text': 'Беспокоят ли вас вены, варикоз, тяжесть в ногах?', 'type': 'single', 'options': ['нет', 'часто', 'иногда']},
                {'str_id': 'general_18', 'text': 'Оцените ваш питьевой режим', 'type': 'single', 'options': ['пью воду адекватно', 'воду не люблю, но пью другие напитки', 'забываю пить', 'не чувствую жажды', 'пью много, жажду сложно утолить']},
                {'str_id': 'general_19', 'text': 'Устраивает ли вас состояние кожи, волос и ногтей?', 'type': 'single', 'options': ['да, всё хорошо', 'есть проблемы с кожей', 'не устраивает состояние волос / ногтей']},
                {'str_id': 'general_20', 'text': 'Беспокоит ли вас запах изо рта, стоматологические или ЛОР-проблемы?', 'type': 'single', 'options': ['да', 'нет']},
                {'str_id': 'general_21', 'text': 'Были ли у вас ортодонтические патологии?', 'type': 'single', 'options': ['да', 'сейчас прохожу лечение', 'уже исправлены', 'нет']},
                {'str_id': 'general_22', 'text': 'Оцените потоотделение', 'type': 'single', 'options': ['сильное с запахом', 'сильное без запаха', 'нормальное', 'слабое']},
                {'str_id': 'general_23', 'text': 'Есть ли у вас зависимости?', 'type': 'multi', 'options': ['нет', 'пищевые', 'курение', 'алкоголь', 'игры', 'гаджеты / соцсети', 'другое']},
                {'str_id': 'general_24', 'text': 'Оцените уровень стресса по шкале от 1 до 10', 'type': 'single', 'options': [str(i) for i in range(1, 11)]},
                {'str_id': 'general_25', 'text': 'Есть ли проблемы опорно-двигательного аппарата?', 'type': 'single', 'options': ['да', 'сейчас нет', 'нет']},
                {'str_id': 'general_26', 'text': 'Были ли серьезные травмы опорно-двигательного аппарата?', 'type': 'single', 'options': ['да', 'нет']},
                {'str_id': 'general_27', 'text': 'Оцените уровень либидо', 'type': 'single', 'options': ['всё отлично', 'устраивает', 'наблюдаю снижение', 'не могу оценить', 'пропустить']},
                {'str_id': 'general_28', 'text': 'Считаете ли вы ваше питание полноценным?', 'type': 'single', 'options': ['нет', 'да, считаю КБЖУ', 'соблюдаю протокол питания', 'стараюсь следить за качеством']},
                {'str_id': 'general_29', 'text': 'Испытываете ли вы трудности с запоминанием информации?', 'type': 'single', 'options': ['да', 'нет']},
                
                # ... (and so on for all other blocks) ...

                {'str_id': 'final_end', 'text': 'Спасибо за заполнение опросника. Мы проанализируем данные и свяжемся с вами.', 'type': 'text'},
            ]

            # Create Question objects and map them
            question_map = {}
            for q_def in question_definitions:
                options_json = json.dumps(q_def.get('options')) if q_def.get('options') else None
                q = Question(
                    questionnaire_id=main_questionnaire.id,
                    text=q_def['text'],
                    type=q_def['type'],
                    options=options_json
                )
                session.add(q)
                question_map[q_def['str_id']] = q
            
            await session.flush() # All questions now have IDs

            # --- Logic Definition ---
            logic_definitions = [
                {'q': 'gender_selection', 'a': 'Мужской', 'next_q': 'general_01'},
                {'q': 'gender_selection', 'a': 'Женский', 'next_q': 'female_01'},
                # ... (all other logic rules from user's text) ...
                {'q': 'oda_07', 'a': 'любой', 'next_q': 'final_end'},
            ]

            for logic_def in logic_definitions:
                question_id = question_map[logic_def['q']].id
                next_question_id = None
                if logic_def.get('next_q'):
                    next_question_id = question_map[logic_def['next_q']].id
                
                session.add(QuestionLogic(
                    question_id=question_id,
                    answer_value=logic_def['a'],
                    next_question_id=next_question_id
                ))

            await session.commit()
            logging.info("Questionnaire data seeded successfully.")

    logging.info("Database initialization complete.")


async def on_startup_webhook(bot: Bot):
    await init_db()
    webhook_url = f"{settings.WEBHOOK_HOST}{settings.WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)
    logging.info(f"Telegram Webhook set to {webhook_url}")

    if settings.YOOKASSA_NOTIFICATION_URL:
        logging.info(f"YooKassa Notifications expected at: {settings.YOOKASSA_NOTIFICATION_URL}")


async def on_shutdown_webhook(bot: Bot):
    logging.info("Shutting down and deleting Telegram webhook...")
    await bot.delete_webhook()
    logging.info("Telegram Webhook deleted.")


async def start_polling(dp: Dispatcher, bot: Bot):
    logging.info("Starting bot in polling mode...")
    await init_db()
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
            logging.warning(f"YooKassa payment {notification.object.id} {notification.event}.")
            # TODO: Implement full handling

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
        asyncio.run(start_polling(dp, bot))


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
