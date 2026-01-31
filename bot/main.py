# VERSION 9: Final explicit logic for init_db and SyntaxError fix
print("---> RUNNING MAIN.PY VERSION 9 ---")
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
            logging.info("Seeding new questionnaire data (explicit logic, compat mode)...")
            main_questionnaire = Questionnaire(title="Основной опросник")
            session.add(main_questionnaire)
            await session.flush()

            question_definitions = [
                {'str_id': 'gender_selection', 'text': 'Пожалуйста, укажите ваш пол:', 'type': 'single'},
                {'str_id': 'general_01', 'text': 'Ваш род занятий, работа', 'type': 'multi'},
                {'str_id': 'general_02', 'text': 'Присутствуют ли в вашей жизни спорт и физическая активность?', 'type': 'single'},
                {'str_id': 'general_03', 'text': 'Если у вас есть или были хронические / наследственные заболевания — укажите какие', 'type': 'text'},
                {'str_id': 'general_04', 'text': 'Есть ли хронические / генетические заболевания у ваших близких родственников?', 'type': 'text'},
                {'str_id': 'general_05', 'text': 'Были ли у вас операции? Какие и как давно?', 'type': 'text'},
                {'str_id': 'general_06', 'text': 'Принимаете ли вы на постоянной основе фармпрепараты или БАДы? Если да — какие', 'type': 'text'},
                {'str_id': 'general_07', 'text': 'Испытываете ли вы симптомы аллергии?', 'type': 'single'},
                {'str_id': 'general_08', 'text': 'Как часто вы переносите сезонные ОРВИ?', 'type': 'single'},
                {'str_id': 'general_09', 'text': 'Кратко опишите ваш режим дня (сон, работа, питание, транспорт, прогулки, хобби)', 'type': 'text'},
                {'str_id': 'general_10', 'text': 'Оцените качество вашего сна', 'type': 'multi'},
                {'str_id': 'general_11', 'text': 'Знакомы ли вы с правилами гигиены сна?', 'type': 'single'},
                {'str_id': 'general_12', 'text': 'Бывают ли у вас мышечные судороги, спазмы, онемение?', 'type': 'multi'},
                {'str_id': 'general_13', 'text': 'Испытываете ли вы головокружение?', 'type': 'single'},
                {'str_id': 'general_14', 'text': 'Знаете ли вы своё артериальное давление и пульс?', 'type': 'single'},
                {'str_id': 'general_15', 'text': 'Беспокоят ли вас отеки?', 'type': 'multi'},
                {'str_id': 'general_16', 'text': 'Бывают ли частые или ночные позывы к мочеиспусканию?', 'type': 'single'},
                {'str_id': 'general_17', 'text': 'Беспокоят ли вас вены, варикоз, тяжесть в ногах?', 'type': 'single'},
                {'str_id': 'general_18', 'text': 'Оцените ваш питьевой режим', 'type': 'single'},
                {'str_id': 'general_19', 'text': 'Устраивает ли вас состояние кожи, волос и ногтей?', 'type': 'single'},
                {'str_id': 'general_20', 'text': 'Беспокоит ли вас запах изо рта, стоматологические или ЛОР-проблемы?', 'type': 'single'},
                {'str_id': 'general_21', 'text': 'Были ли у вас ортодонтические патологии?', 'type': 'single'},
                {'str_id': 'general_22', 'text': 'Оцените потоотделение', 'type': 'single'},
                {'str_id': 'general_23', 'text': 'Есть ли у вас зависимости?', 'type': 'multi'},
                {'str_id': 'general_24', 'text': 'Оцените уровень стресса по шкале от 1 до 10', 'type': 'single'},
                {'str_id': 'general_25', 'text': 'Есть ли проблемы опорно-двигательного аппарата?', 'type': 'single'},
                {'str_id': 'general_26', 'text': 'Были ли серьезные травмы опорно-двигательного аппарата?', 'type': 'single'},
                {'str_id': 'general_27', 'text': 'Оцените уровень либидо', 'type': 'single'},
                {'str_id': 'general_28', 'text': 'Считаете ли вы ваше питание полноценным?', 'type': 'single'},
                {'str_id': 'general_29', 'text': 'Испытываете ли вы трудности с запоминанием информации?', 'type': 'single'},
                {'str_id': 'gkt_01', 'text': 'Испытываете ли вы болевые ощущения или дискомфорт в животе?', 'type': 'multi'},
                {'str_id': 'gkt_02', 'text': 'Связаны ли боли с приемом пищи?', 'type': 'single'},
                {'str_id': 'gkt_03', 'text': 'Беспокоят ли изжога, жжение за грудиной, отрыжка, нарушение глотания?', 'type': 'single'},
                {'str_id': 'gkt_04', 'text': 'Бывает ли вздутие живота, метеоризм?', 'type': 'single'},
                {'str_id': 'gkt_05', 'text': 'Оцените ваш аппетит', 'type': 'single'},
                {'str_id': 'gkt_06', 'text': 'Какая регулярность стула?', 'type': 'single'},
                {'str_id': 'gkt_07', 'text': 'Оцените характер стула', 'type': 'single'},
                {'str_id': 'gkt_08', 'text': 'Испытываете ли вы тошноту?', 'type': 'multi'},
                {'str_id': 'gkt_09', 'text': 'Как переносите пропуск приема пищи?', 'type': 'single'},
                {'str_id': 'gkt_10', 'text': 'Бывает ли сонливость или упадок энергии после еды?', 'type': 'single'},
                {'str_id': 'gkt_11', 'text': 'Есть ли продукты, после которых вам становится хуже?', 'type': 'single'},
                {'str_id': 'skin_01', 'text': 'Что вас не устраивает в состоянии кожи?', 'type': 'multi'},
                {'str_id': 'skin_02', 'text': 'Обращались ли вы к специалисту по поводу кожи?', 'type': 'single'},
                {'str_id': 'nervous_01', 'text': 'Как вы оцениваете свою память?', 'type': 'multi'},
                {'str_id': 'nervous_02', 'text': 'Бывают ли тики, непроизвольные движения?', 'type': 'single'},
                {'str_id': 'nervous_03', 'text': 'Как вы чувствуете себя в общении?', 'type': 'single'},
                {'str_id': 'nervous_04', 'text': 'Вас устраивает ваше эмоциональное состояние?', 'type': 'single'},
                {'str_id': 'nervous_05', 'text': 'Как вы реагируете на стресс?', 'type': 'single'},
                {'str_id': 'nervous_06', 'text': 'Есть ли у вас навыки стресс-менеджмента?', 'type': 'single'},
                {'str_id': 'nervous_07', 'text': 'Как вы принимаете решения?', 'type': 'single'},
                {'str_id': 'nervous_08', 'text': 'Устраивает ли вас умственная работоспособность?', 'type': 'single'},
                {'str_id': 'anemia_01', 'text': 'Беспокоит ли вас слабость, быстрая утомляемость?', 'type': 'single'},
                {'str_id': 'anemia_02', 'text': 'Есть ли бледность кожи, выпадение волос?', 'type': 'single'},
                {'str_id': 'anemia_03', 'text': 'Бывают ли необычные вкусовые желания (мел, лед и т.п.)?', 'type': 'single'},
                {'str_id': 'anemia_04', 'text': 'Есть ли одышка или сердцебиение при легкой нагрузке?', 'type': 'single'},
                {'str_id': 'anemia_05', 'text': 'Тянет ли вас к запахам (лак, бензин и т.п.)?', 'type': 'single'},
                {'str_id': 'anemia_06', 'text': 'Бывают ли заеды в уголках рта?', 'type': 'single'},
                {'str_id': 'anemia_07', 'text': 'Есть ли отвращение к мясу или продуктам?', 'type': 'single'},
                {'str_id': 'anemia_08', 'text': 'Ощущаете ли зябкость рук и ног?', 'type': 'single'},
                {'str_id': 'female_01', 'text': 'Укажите возраст первой менструации (менархе)', 'type': 'text'},
                {'str_id': 'female_02', 'text': 'Сейчас у вас:', 'type': 'single'},
                {'str_id': 'female_03', 'text': 'Были ли беременности или роды?', 'type': 'single'},
                {'str_id': 'female_04', 'text': 'Продолжительность цикла (в днях)', 'type': 'text'},
                {'str_id': 'female_05', 'text': 'Продолжительность менструации', 'type': 'single'},
                {'str_id': 'female_06', 'text': 'Есть ли симптомы ПМС?', 'type': 'multi'},
                {'str_id': 'female_07', 'text': 'Бывают ли проблемы со сном в период менструации?', 'type': 'single'},
                {'str_id': 'female_08', 'text': 'Оцените обильность выделений (1–10)', 'type': 'single'},
                {'str_id': 'female_09', 'text': 'Оцените болезненность (1–10)', 'type': 'single'},
                {'str_id': 'female_10', 'text': 'Характер выделений', 'type': 'single'},
                {'str_id': 'female_11', 'text': 'Есть ли межменструальные кровянистые выделения?', 'type': 'single'},
                {'str_id': 'female_12', 'text': 'Бывают ли проявления цистита?', 'type': 'single'},
                {'str_id': 'female_13', 'text': 'Беспокоят ли симптомы молочницы / дисбиоза?', 'type': 'single'},
                {'str_id': 'oda_01', 'text': 'Где вас беспокоят боли?', 'type': 'multi'},
                {'str_id': 'oda_02', 'text': 'Оцените интенсивность боли (1–10)', 'type': 'single'},
                {'str_id': 'oda_03', 'text': 'Есть ли скованность суставов?', 'type': 'multi'},
                {'str_id': 'oda_04', 'text': 'Есть ли диагностированные заболевания ОДА?', 'type': 'single'},
                {'str_id': 'oda_05', 'text': 'Есть ли патологии стопы?', 'type': 'single'},
                {'str_id': 'oda_06', 'text': 'Изменился ли размер обуви?', 'type': 'single'},
                {'str_id': 'oda_07', 'text': 'Обращались ли вы к специалистам?', 'type': 'multi'},
                {'str_id': 'final_end', 'text': 'Спасибо за заполнение опросника. Мы проанализируем данные и свяжемся с вами.', 'type': 'text'},
            ]

            question_map = {}
            for q_def in question_definitions:
                q = Question(questionnaire_id=main_questionnaire.id, text=q_def['text'], type=q_def['type'])
                session.add(q)
                question_map[q_def['str_id']] = q
            
            await session.flush()

            logic_definitions = [
                {'q': 'gender_selection', 'a': 'Мужской', 'next_q': 'general_01'},
                {'q': 'gender_selection', 'a': 'Женский', 'next_q': 'female_01'},
                {'q': 'general_01', 'a': 'любой', 'next_q': 'general_02'},
                {'q': 'general_02', 'a': 'да, регулярно', 'next_q': 'general_03'},
                {'q': 'general_02', 'a': 'нерегулярно, время от времени', 'next_q': 'general_03'},
                {'q': 'general_02', 'a': 'нет и не было', 'next_q': 'general_03'},
                {'q': 'general_02', 'a': 'я профессиональный спортсмен', 'next_q': 'general_03'},
                {'q': 'general_03', 'a': 'любой', 'next_q': 'general_04'},
                {'q': 'general_04', 'a': 'любой', 'next_q': 'general_05'},
                {'q': 'general_05', 'a': 'любой', 'next_q': 'general_06'},
                {'q': 'general_06', 'a': 'любой', 'next_q': 'general_07'},
                {'q': 'general_07', 'a': 'очень часто', 'next_q': 'general_08'},
                {'q': 'general_07', 'a': 'иногда', 'next_q': 'general_08'},
                {'q': 'general_07', 'a': 'сезонно', 'next_q': 'general_08'},
                {'q': 'general_07', 'a': 'нет', 'next_q': 'general_08'},
                {'q': 'general_08', 'a': 'очень редко', 'next_q': 'general_09'},
                {'q': 'general_08', 'a': '1–2 раза в год', 'next_q': 'general_09'},
                {'q': 'general_08', 'a': '3–4 раза в год', 'next_q': 'anemia_01'},
                {'q': 'general_08', 'a': 'постоянно, даже летом', 'next_q': 'anemia_01'},
                {'q': 'general_09', 'a': 'любой', 'next_q': 'general_10'},
                {'q': 'general_10', 'a': 'любой', 'next_q': 'general_11'},
                {'q': 'general_11', 'a': 'да, стараюсь придерживаться', 'next_q': 'general_12'},
                {'q': 'general_11', 'a': 'да, но не получается соблюдать', 'next_q': 'general_12'},
                {'q': 'general_11', 'a': 'нет, не знаком', 'next_q': 'general_12'},
                {'q': 'general_12', 'a': 'любой', 'next_q': 'general_13'},
                {'q': 'general_13', 'a': 'да, часто', 'next_q': 'nervous_01'},
                {'q': 'general_13', 'a': 'иногда', 'next_q': 'nervous_01'},
                {'q': 'general_13', 'a': 'нет', 'next_q': 'general_14'},
                {'q': 'general_14', 'a': 'не знаю', 'next_q': 'general_15'},
                {'q': 'general_14', 'a': 'повышенное / гипертония', 'next_q': 'general_15'},
                {'q': 'general_14', 'a': 'есть трекер', 'next_q': 'general_15'},
                {'q': 'general_14', 'a': 'пониженное', 'next_q': 'anemia_01'},
                {'q': 'general_14', 'a': 'нестабильное', 'next_q': 'anemia_01'},
                {'q': 'general_15', 'a': 'любой', 'next_q': 'general_16'},
                {'q': 'general_16', 'a': 'да', 'next_q': 'general_17'},
                {'q': 'general_16', 'a': 'иногда', 'next_q': 'general_17'},
                {'q': 'general_16', 'a': 'нет', 'next_q': 'general_17'},
                {'q': 'general_17', 'a': 'нет', 'next_q': 'general_18'},
                {'q': 'general_17', 'a': 'часто', 'next_q': 'general_18'},
                {'q': 'general_17', 'a': 'иногда', 'next_q': 'general_18'},
                {'q': 'general_18', 'a': 'любой', 'next_q': 'general_19'},
                {'q': 'general_19', 'a': 'да, всё хорошо', 'next_q': 'general_20'},
                {'q': 'general_19', 'a': 'есть проблемы с кожей', 'next_q': 'skin_01'},
                {'q': 'general_19', 'a': 'не устраивает состояние волос / ногтей', 'next_q': 'anemia_01'},
                {'q': 'general_20', 'a': 'любой', 'next_q': 'general_21'},
                {'q': 'general_21', 'a': 'любой', 'next_q': 'general_22'},
                {'q': 'general_22', 'a': 'любой', 'next_q': 'general_23'},
                {'q': 'general_23', 'a': 'нет', 'next_q': 'general_24'},
                {'q': 'general_23', 'a': 'любой', 'next_q': 'nervous_01'},
                {'q': 'general_24', 'a': 'любой', 'next_q': 'general_25'},
                {'q': 'general_25', 'a': 'да', 'next_q': 'oda_01'},
                {'q': 'general_25', 'a': 'любой', 'next_q': 'general_26'},
                {'q': 'general_26', 'a': 'любой', 'next_q': 'general_27'},
                {'q': 'general_27', 'a': 'любой', 'next_q': 'general_28'},
                {'q': 'general_28', 'a': 'любой', 'next_q': 'general_29'},
                {'q': 'general_29', 'a': 'да', 'next_q': 'nervous_01'},
                {'q': 'general_29', 'a': 'нет', 'next_q': 'gkt_01'},
                {'q': 'gkt_01', 'a': 'нет', 'next_q': 'gkt_03'},
                {'q': 'gkt_01', 'a': 'любой', 'next_q': 'gkt_02'},
                {'q': 'gkt_02', 'a': 'любой', 'next_q': 'gkt_03'},
                {'q': 'gkt_03', 'a': 'любой', 'next_q': 'gkt_04'},
                {'q': 'gkt_04', 'a': 'любой', 'next_q': 'gkt_05'},
                {'q': 'gkt_05', 'a': 'любой', 'next_q': 'gkt_06'},
                {'q': 'gkt_06', 'a': 'любой', 'next_q': 'gkt_07'},
                {'q': 'gkt_07', 'a': 'любой', 'next_q': 'gkt_08'},
                {'q': 'gkt_08', 'a': 'любой', 'next_q': 'gkt_09'},
                {'q': 'gkt_09', 'a': 'любой', 'next_q': 'gkt_10'},
                {'q': 'gkt_10', 'a': 'любой', 'next_q': 'gkt_11'},
                {'q': 'gkt_11', 'a': 'любой', 'next_q': 'skin_01'},
                {'q': 'skin_01', 'a': 'любой', 'next_q': 'skin_02'},
                {'q': 'skin_02', 'a': 'любой', 'next_q': 'nervous_01'},
                {'q': 'nervous_01', 'a': 'любой', 'next_q': 'nervous_02'},
                {'q': 'nervous_02', 'a': 'любой', 'next_q': 'nervous_03'},
                {'q': 'nervous_03', 'a': 'любой', 'next_q': 'nervous_04'},
                {'q': 'nervous_04', 'a': 'любой', 'next_q': 'nervous_05'},
                {'q': 'nervous_05', 'a': 'любой', 'next_q': 'nervous_06'},
                {'q': 'nervous_06', 'a': 'любой', 'next_q': 'nervous_07'},
                {'q': 'nervous_07', 'a': 'любой', 'next_q': 'nervous_08'},
                {'q': 'nervous_08', 'a': 'любой', 'next_q': 'anemia_01'},
                {'q': 'anemia_01', 'a': 'любой', 'next_q': 'anemia_02'},
                {'q': 'anemia_02', 'a': 'любой', 'next_q': 'anemia_03'},
                {'q': 'anemia_03', 'a': 'любой', 'next_q': 'anemia_04'},
                {'q': 'anemia_04', 'a': 'любой', 'next_q': 'anemia_05'},
                {'q': 'anemia_05', 'a': 'любой', 'next_q': 'anemia_06'},
                {'q': 'anemia_06', 'a': 'любой', 'next_q': 'anemia_07'},
                {'q': 'anemia_07', 'a': 'любой', 'next_q': 'anemia_08'},
                {'q': 'anemia_08', 'a': 'любой', 'next_q': 'oda_01'},
                {'q': 'female_01', 'a': 'любой', 'next_q': 'female_02'},
                {'q': 'female_02', 'a': 'любой', 'next_q': 'female_03'},
                {'q': 'female_03', 'a': 'любой', 'next_q': 'female_04'},
                {'q': 'female_04', 'a': 'любой', 'next_q': 'female_05'},
                {'q': 'female_05', 'a': 'любой', 'next_q': 'female_06'},
                {'q': 'female_06', 'a': 'любой', 'next_q': 'female_07'},
                {'q': 'female_07', 'a': 'любой', 'next_q': 'female_08'},
                {'q': 'female_08', 'a': 'любой', 'next_q': 'female_09'},
                {'q': 'female_09', 'a': 'любой', 'next_q': 'female_10'},
                {'q': 'female_10', 'a': 'любой', 'next_q': 'female_11'},
                {'q': 'female_11', 'a': 'любой', 'next_q': 'female_12'},
                {'q': 'female_12', 'a': 'любой', 'next_q': 'female_13'},
                {'q': 'female_13', 'a': 'любой', 'next_q': 'oda_01'},
                {'q': 'oda_01', 'a': 'любой', 'next_q': 'oda_02'},
                {'q': 'oda_02', 'a': 'любой', 'next_q': 'oda_03'},
                {'q': 'oda_03', 'a': 'любой', 'next_q': 'oda_04'},
                {'q': 'oda_04', 'a': 'любой', 'next_q': 'oda_05'},
                {'q': 'oda_05', 'a': 'любой', 'next_q': 'oda_06'},
                {'q': 'oda_06', 'a': 'любой', 'next_q': 'oda_07'},
                {'q': 'oda_07', 'a': 'любой', 'next_q': 'final_end'},
                {'q': 'final_end', 'a': 'любой', 'next_q': None},
            ]

            for logic_def in logic_definitions:
                question_id = question_map[logic_def['q']].id
                next_question_id = None
                if logic_def.get('next_q'):
                    next_question_id = question_map[logic_def['next_q']].id
                
                existing_logic = await session.execute(
                    select(QuestionLogic).where(
                        QuestionLogic.question_id == question_id,
                        QuestionLogic.answer_value == logic_def['a']
                    )
                )
                if existing_logic.scalar_one_or_none() is None:
                    session.add(QuestionLogic(
                        question_id=question_id,
                        answer_value=logic_def['a'],
                        next_question_id=next_question_id
                    ))

            await session.commit()
            logging.info("Questionnaire data seeded successfully (compat mode).")

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
                        
                        admin_notification_text = (
                            f"💰 <b>НОВОЕ УВЕДОМЛЕНИЕ ОТ ЮKASSA: Оплата подтверждена!</b>\n\n"
                            f"Пользователь: {user.username or 'N/A'} (ID: <code>{user.telegram_id}</code>)\n"
                            f"Сумма: {notification.object.amount.value} {notification.object.amount.currency}\n"
                            f"YooKassa Payment ID: <code>{payment_id_yk}</code>"
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