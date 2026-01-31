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
            await session.flush() # Assigns ID to main_questionnaire

            # Define all questions with string IDs
            question_definitions = [
                {'str_id': 'gender_selection', 'text': 'Пожалуйста, укажите ваш пол:', 'type': 'single'},
                # GENERAL BLOCK
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
                {'str_id': 'general_24', 'text': 'Оцените уровень стресса по шкале от 1 до 10', 'type': 'single', 'options': ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']},
                {'str_id': 'general_25', 'text': 'Есть ли проблемы опорно-двигательного аппарата?', 'type': 'single'},
                {'str_id': 'general_26', 'text': 'Были ли серьезные травмы опорно-двигательного аппарата?', 'type': 'single'},
                {'str_id': 'general_27', 'text': 'Оцените уровень либидо', 'type': 'single'},
                {'str_id': 'general_28', 'text': 'Считаете ли вы ваше питание полноценным?', 'type': 'single'},
                {'str_id': 'general_29', 'text': 'Испытываете ли вы трудности с запоминанием информации?', 'type': 'single'},
                
                # GKT BLOCK
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

                # SKIN BLOCK
                {'str_id': 'skin_01', 'text': 'Что вас не устраивает в состоянии кожи?', 'type': 'multi'},
                {'str_id': 'skin_02', 'text': 'Обращались ли вы к специалисту по поводу кожи?', 'type': 'single'},

                # NERVOUS SYSTEM BLOCK
                {'str_id': 'nervous_01', 'text': 'Как вы оцениваете свою память?', 'type': 'multi'},
                {'str_id': 'nervous_02', 'text': 'Бывают ли тики, непроизвольные движения?', 'type': 'single'},
                {'str_id': 'nervous_03', 'text': 'Как вы чувствуете себя в общении?', 'type': 'single'},
                {'str_id': 'nervous_04', 'text': 'Вас устраивает ваше эмоциональное состояние?', 'type': 'single'},
                {'str_id': 'nervous_05', 'text': 'Как вы реагируете на стресс?', 'type': 'single'},
                {'str_id': 'nervous_06', 'text': 'Есть ли у вас навыки стресс-менеджмента?', 'type': 'single'},
                {'str_id': 'nervous_07', 'text': 'Как вы принимаете решения?', 'type': 'single'},
                {'str_id': 'nervous_08', 'text': 'Устраивает ли вас умственная работоспособность?', 'type': 'single'},

                # ANEMIA BLOCK
                {'str_id': 'anemia_01', 'text': 'Беспокоит ли вас слабость, быстрая утомляемость?', 'type': 'single'},
                {'str_id': 'anemia_02', 'text': 'Есть ли бледность кожи, выпадение волос?', 'type': 'single'},
                {'str_id': 'anemia_03', 'text': 'Бывают ли необычные вкусовые желания (мел, лед и т.п.)?', 'type': 'single'},
                {'str_id': 'anemia_04', 'text': 'Есть ли одышка или сердцебиение при легкой нагрузке?', 'type': 'single'},
                {'str_id': 'anemia_05', 'text': 'Тянет ли вас к запахам (лак, бензин и т.п.)?', 'type': 'single'},
                {'str_id': 'anemia_06', 'text': 'Бывают ли заеды в уголках рта?', 'type': 'single'},
                {'str_id': 'anemia_07', 'text': 'Есть ли отвращение к мясу или продуктам?', 'type': 'single'},
                {'str_id': 'anemia_08', 'text': 'Ощущаете ли зябкость рук и ног?', 'type': 'single'},

                # FEMALE BLOCK
                {'str_id': 'female_01', 'text': 'Укажите возраст первой менструации (менархе)', 'type': 'text'},
                {'str_id': 'female_02', 'text': 'Сейчас у вас:', 'type': 'single'},
                {'str_id': 'female_03', 'text': 'Были ли беременности или роды?', 'type': 'single'},
                {'str_id': 'female_04', 'text': 'Продолжительность цикла (в днях)', 'type': 'text'},
                {'str_id': 'female_05', 'text': 'Продолжительность менструации', 'type': 'single'},
                {'str_id': 'female_06', 'text': 'Есть ли симптомы ПМС?', 'type': 'multi'},
                {'str_id': 'female_07', 'text': 'Бывают ли проблемы со сном в период менструации?', 'type': 'single'},
                {'str_id': 'female_08', 'text': 'Оцените обильность выделений (1–10)', 'type': 'single', 'options': ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']},
                {'str_id': 'female_09', 'text': 'Оцените болезненность (1–10)', 'type': 'single', 'options': ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']},
                {'str_id': 'female_10', 'text': 'Характер выделений', 'type': 'single'},
                {'str_id': 'female_11', 'text': 'Есть ли межменструальные кровянистые выделения?', 'type': 'single'},
                {'str_id': 'female_12', 'text': 'Бывают ли проявления цистита?', 'type': 'single'},
                {'str_id': 'female_13', 'text': 'Беспокоят ли симптомы молочницы / дисбиоза?', 'type': 'single'},

                # ODA BLOCK
                {'str_id': 'oda_01', 'text': 'Где вас беспокоят боли?', 'type': 'multi'},
                {'str_id': 'oda_02', 'text': 'Оцените интенсивность боли (1–10)', 'type': 'single', 'options': ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']},
                {'str_id': 'oda_03', 'text': 'Есть ли скованность суставов?', 'type': 'multi'},
                {'str_id': 'oda_04', 'text': 'Есть ли диагностированные заболевания ОДА?', 'type': 'single'},
                {'str_id': 'oda_05', 'text': 'Есть ли патологии стопы?', 'type': 'single'},
                {'str_id': 'oda_06', 'text': 'Изменился ли размер обуви?', 'type': 'single'},
                {'str_id': 'oda_07', 'text': 'Обращались ли вы к специалистам?', 'type': 'multi'},

                # FINAL
                {'str_id': 'final_end', 'text': 'Спасибо за заполнение опросника. Мы проанализируем данные и свяжемся с вами.', 'type': 'text'},
            ]

            # Store questions in session to get their IDs
            for q_def in question_definitions:
                q = Question(questionnaire_id=main_questionnaire.id, text=q_def['text'], type=q_def['type'])
                session.add(q)
                # Temporarily store the object for ID lookup
                q_def['obj'] = q 
            
            await session.flush() # All questions now have their IDs assigned

            # Create a map from string_id to integer_id
            question_id_map = {q_def['str_id']: q_def['obj'].id for q_def in question_definitions}

            # --- Logic Definition ---
            logic_definitions = [
                # Gender Selection Logic
                {'q_str': 'gender_selection', 'ans': 'Мужской', 'next_q_str': 'general_01'},
                {'q_str': 'gender_selection', 'ans': 'Женский', 'next_q_str': 'female_01'},

                # GENERAL BLOCK Logic
                {'q_str': 'general_01', 'ans': 'любой', 'next_q_str': 'general_02'},
                {'q_str': 'general_02', 'ans': 'да, регулярно', 'next_q_str': 'general_03'},
                {'q_str': 'general_02', 'ans': 'нерегулярно, время от времени', 'next_q_str': 'general_03'},
                {'q_str': 'general_02', 'ans': 'нет и не было', 'next_q_str': 'general_03'},
                {'q_str': 'general_02', 'ans': 'я профессиональный спортсмен', 'next_q_str': 'general_03'},
                {'q_str': 'general_03', 'ans': 'любой', 'next_q_str': 'general_04'},
                {'q_str': 'general_04', 'ans': 'любой', 'next_q_str': 'general_05'},
                {'q_str': 'general_05', 'ans': 'любой', 'next_q_str': 'general_06'},
                {'q_str': 'general_06', 'ans': 'любой', 'next_q_str': 'general_07'},
                {'q_str': 'general_07', 'ans': 'очень часто', 'next_q_str': 'general_08'},
                {'q_str': 'general_07', 'ans': 'иногда', 'next_q_str': 'general_08'},
                {'q_str': 'general_07', 'ans': 'сезонно', 'next_q_str': 'general_08'},
                {'q_str': 'general_07', 'ans': 'нет', 'next_q_str': 'general_08'},
                {'q_str': 'general_08', 'ans': 'очень редко', 'next_q_str': 'general_09'},
                {'q_str': 'general_08', 'ans': '1–2 раза в год', 'next_q_str': 'general_09'},
                {'q_str': 'general_08', 'ans': '3–4 раза в год', 'next_q_str': 'anemia_01'},
                {'q_str': 'general_08', 'ans': 'постоянно, даже летом', 'next_q_str': 'anemia_01'},
                {'q_str': 'general_09', 'ans': 'любой', 'next_q_str': 'general_10'},
                {'q_str': 'general_10', 'ans': 'любой', 'next_q_str': 'general_11'}, # multi-choice "any" transitions
                {'q_str': 'general_11', 'ans': 'да, стараюсь придерживаться', 'next_q_str': 'general_12'},
                {'q_str': 'general_11', 'ans': 'да, но не получается соблюдать', 'next_q_str': 'general_12'},
                {'q_str': 'general_11', 'ans': 'нет, не знаком', 'next_q_str': 'general_12'},
                {'q_str': 'general_12', 'ans': 'любой', 'next_q_str': 'general_13'}, # multi-choice "any" transitions
                {'q_str': 'general_13', 'ans': 'да, часто', 'next_q_str': 'nervous_01'},
                {'q_str': 'general_13', 'ans': 'иногда', 'next_q_str': 'nervous_01'},
                {'q_str': 'general_13', 'ans': 'нет', 'next_q_str': 'general_14'},
                {'q_str': 'general_14', 'ans': 'не знаю', 'next_q_str': 'general_15'},
                {'q_str': 'general_14', 'ans': 'повышенное / гипертония', 'next_q_str': 'general_15'},
                {'q_str': 'general_14', 'ans': 'пониженное', 'next_q_str': 'anemia_01'},
                {'q_str': 'general_14', 'ans': 'нестабильное', 'next_q_str': 'anemia_01'},
                {'q_str': 'general_14', 'ans': 'есть трекер', 'next_q_str': 'general_15'},
                {'q_str': 'general_15', 'ans': 'любой', 'next_q_str': 'general_16'}, # multi-choice "any" transitions
                {'q_str': 'general_16', 'ans': 'да', 'next_q_str': 'general_17'},
                {'q_str': 'general_16', 'ans': 'иногда', 'next_q_str': 'general_17'},
                {'q_str': 'general_16', 'ans': 'нет', 'next_q_str': 'general_17'},
                {'q_str': 'general_17', 'ans': 'нет', 'next_q_str': 'general_18'},
                {'q_str': 'general_17', 'ans': 'часто', 'next_q_str': 'general_18'},
                {'q_str': 'general_17', 'ans': 'иногда', 'next_q_str': 'general_18'},
                {'q_str': 'general_18', 'ans': 'пью воду адекватно', 'next_q_str': 'general_19'},
                {'q_str': 'general_18', 'ans': 'воду не люблю, но пью другие напитки', 'next_q_str': 'general_19'},
                {'q_str': 'general_18', 'ans': 'забываю пить', 'next_q_str': 'general_19'},
                {'q_str': 'general_18', 'ans': 'не чувствую жажды', 'next_q_str': 'general_19'},
                {'q_str': 'general_18', 'ans': 'пью много, жажду сложно утолить', 'next_q_str': 'general_19'},
                {'q_str': 'general_19', 'ans': 'да, всё хорошо', 'next_q_str': 'general_20'},
                {'q_str': 'general_19', 'ans': 'есть проблемы с кожей', 'next_q_str': 'skin_01'},
                {'q_str': 'general_19', 'ans': 'не устраивает состояние волос / ногтей', 'next_q_str': 'anemia_01'},
                {'q_str': 'general_20', 'ans': 'да', 'next_q_str': 'general_21'},
                {'q_str': 'general_20', 'ans': 'нет', 'next_q_str': 'general_21'},
                {'q_str': 'general_21', 'ans': 'да', 'next_q_str': 'general_22'},
                {'q_str': 'general_21', 'ans': 'сейчас прохожу лечение', 'next_q_str': 'general_22'},
                {'q_str': 'general_21', 'ans': 'уже исправлены', 'next_q_str': 'general_22'},
                {'q_str': 'general_21', 'ans': 'нет', 'next_q_str': 'general_22'},
                {'q_str': 'general_22', 'ans': 'сильное с запахом', 'next_q_str': 'general_23'},
                {'q_str': 'general_22', 'ans': 'сильное без запаха', 'next_q_str': 'general_23'},
                {'q_str': 'general_22', 'ans': 'нормальное', 'next_q_str': 'general_23'},
                {'q_str': 'general_22', 'ans': 'слабое', 'next_q_str': 'general_23'},
                {'q_str': 'general_23', 'ans': 'нет', 'next_q_str': 'general_24'},
                {'q_str': 'general_23', 'ans': 'любой', 'next_q_str': 'nervous_01'}, # any(except "нет") -> nervous_01
                {'q_str': 'general_24', 'ans': '7–10', 'next_q_str': 'nervous_01'},
                {'q_str': 'general_24', 'ans': '1–6', 'next_q_str': 'general_25'},
                {'q_str': 'general_25', 'ans': 'да', 'next_q_str': 'oda_01'},
                {'q_str': 'general_25', 'ans': 'сейчас нет', 'next_q_str': 'general_26'},
                {'q_str': 'general_25', 'ans': 'нет', 'next_q_str': 'general_26'},
                {'q_str': 'general_26', 'ans': 'да', 'next_q_str': 'general_27'},
                {'q_str': 'general_26', 'ans': 'нет', 'next_q_str': 'general_27'},
                {'q_str': 'general_27', 'ans': 'всё отлично', 'next_q_str': 'general_28'},
                {'q_str': 'general_27', 'ans': 'устраивает', 'next_q_str': 'general_28'},
                {'q_str': 'general_27', 'ans': 'наблюдаю снижение', 'next_q_str': 'general_28'},
                {'q_str': 'general_27', 'ans': 'не могу оценить', 'next_q_str': 'general_28'},
                {'q_str': 'general_27', 'ans': 'пропустить', 'next_q_str': 'general_28'},
                {'q_str': 'general_28', 'ans': 'нет', 'next_q_str': 'general_29'},
                {'q_str': 'general_28', 'ans': 'да, считаю КБЖУ', 'next_q_str': 'general_29'},
                {'q_str': 'general_28', 'ans': 'соблюдаю протокол питания', 'next_q_str': 'general_29'},
                {'q_str': 'general_28', 'ans': 'стараюсь следить за качеством', 'next_q_str': 'general_29'},
                {'q_str': 'general_29', 'ans': 'да', 'next_q_str': 'nervous_01'},
                {'q_str': 'general_29', 'ans': 'нет', 'next_q_str': 'gkt_01'},
                
                # GKT BLOCK Logic
                {'q_str': 'gkt_01', 'ans': 'нет', 'next_q_str': 'gkt_03'},
                {'q_str': 'gkt_01', 'ans': 'любой', 'next_q_str': 'gkt_02'}, # any(except "нет") -> gkt_02
                {'q_str': 'gkt_02', 'ans': 'сразу после еды', 'next_q_str': 'gkt_03'},
                {'q_str': 'gkt_02', 'ans': 'через 1–2 часа', 'next_q_str': 'gkt_03'},
                {'q_str': 'gkt_02', 'ans': 'связаны с голодом', 'next_q_str': 'gkt_03'},
                {'q_str': 'gkt_02', 'ans': 'не связаны', 'next_q_str': 'gkt_03'},
                {'q_str': 'gkt_02', 'ans': 'бывает по-разному', 'next_q_str': 'gkt_03'},
                {'q_str': 'gkt_03', 'ans': 'часто', 'next_q_str': 'gkt_04'},
                {'q_str': 'gkt_03', 'ans': 'иногда', 'next_q_str': 'gkt_04'},
                {'q_str': 'gkt_03', 'ans': 'нет', 'next_q_str': 'gkt_04'},
                {'q_str': 'gkt_04', 'ans': 'нет', 'next_q_str': 'gkt_05'},
                {'q_str': 'gkt_04', 'ans': 'иногда', 'next_q_str': 'gkt_05'},
                {'q_str': 'gkt_04', 'ans': 'постоянно', 'next_q_str': 'gkt_05'},
                {'q_str': 'gkt_05', 'ans': 'стабильный, хороший', 'next_q_str': 'gkt_06'},
                {'q_str': 'gkt_05', 'ans': 'постоянно хочется есть', 'next_q_str': 'gkt_06'},
                {'q_str': 'gkt_05', 'ans': 'плохой', 'next_q_str': 'gkt_06'},
                {'q_str': 'gkt_05', 'ans': 'нестабильный', 'next_q_str': 'gkt_06'},
                {'q_str': 'gkt_06', 'ans': 'ежедневно утром', 'next_q_str': 'gkt_07'},
                {'q_str': 'gkt_06', 'ans': 'ежедневно в разное время', 'next_q_str': 'gkt_07'},
                {'q_str': 'gkt_06', 'ans': 'несколько раз в день', 'next_q_str': 'gkt_07'},
                {'q_str': 'gkt_06', 'ans': 'непредсказуемый', 'next_q_str': 'gkt_07'},
                {'q_str': 'gkt_06', 'ans': 'не каждый день', 'next_q_str': 'gkt_07'},
                {'q_str': 'gkt_07', 'ans': 'нормальный', 'next_q_str': 'gkt_08'},
                {'q_str': 'gkt_07', 'ans': 'склонность к диарее', 'next_q_str': 'gkt_08'},
                {'q_str': 'gkt_07', 'ans': 'плотный, сухой', 'next_q_str': 'gkt_08'},
                {'q_str': 'gkt_07', 'ans': 'нестабильный', 'next_q_str': 'gkt_08'},
                {'q_str': 'gkt_07', 'ans': 'есть примеси', 'next_q_str': 'gkt_08'},
                {'q_str': 'gkt_08', 'ans': 'любой', 'next_q_str': 'gkt_09'}, # multi-choice "any" transitions
                {'q_str': 'gkt_09', 'ans': 'нормально', 'next_q_str': 'gkt_10'},
                {'q_str': 'gkt_09', 'ans': 'головокружение, слабость', 'next_q_str': 'gkt_10'},
                {'q_str': 'gkt_09', 'ans': 'очень плохо', 'next_q_str': 'gkt_10'},
                {'q_str': 'gkt_10', 'ans': 'да', 'next_q_str': 'gkt_11'},
                {'q_str': 'gkt_10', 'ans': 'нет', 'next_q_str': 'gkt_11'},
                {'q_str': 'gkt_10', 'ans': 'редко после обильной еды', 'next_q_str': 'gkt_11'},
                {'q_str': 'gkt_11', 'ans': 'да', 'next_q_str': 'skin_01'},
                {'q_str': 'gkt_11', 'ans': 'нет', 'next_q_str': 'skin_01'},

                # SKIN BLOCK Logic
                {'q_str': 'skin_01', 'ans': 'любой', 'next_q_str': 'skin_02'}, # multi-choice "any" transitions
                {'q_str': 'skin_02', 'ans': 'да', 'next_q_str': 'nervous_01'},
                {'q_str': 'skin_02', 'ans': 'нет', 'next_q_str': 'nervous_01'},
                {'q_str': 'skin_02', 'ans': 'постоянно наблюдаюсь', 'next_q_str': 'nervous_01'},

                # NERVOUS SYSTEM BLOCK Logic
                {'q_str': 'nervous_01', 'ans': 'любой', 'next_q_str': 'nervous_02'}, # multi-choice "any" transitions
                {'q_str': 'nervous_02', 'ans': 'да', 'next_q_str': 'nervous_03'},
                {'q_str': 'nervous_02', 'ans': 'иногда', 'next_q_str': 'nervous_03'},
                {'q_str': 'nervous_02', 'ans': 'нет', 'next_q_str': 'nervous_03'},
                {'q_str': 'nervous_03', 'ans': 'легко общаюсь', 'next_q_str': 'nervous_04'},
                {'q_str': 'nervous_03', 'ans': 'быстро устаю', 'next_q_str': 'nervous_04'},
                {'q_str': 'nervous_03', 'ans': 'комфортно одному', 'next_q_str': 'nervous_04'},
                {'q_str': 'nervous_03', 'ans': 'не могу без общения', 'next_q_str': 'nervous_04'},
                {'q_str': 'nervous_04', 'ans': 'да', 'next_q_str': 'nervous_05'},
                {'q_str': 'nervous_04', 'ans': 'нет', 'next_q_str': 'nervous_05'},
                {'q_str': 'nervous_04', 'ans': 'наблюдаюсь у психотерапевта', 'next_q_str': 'nervous_05'},
                {'q_str': 'nervous_05', 'ans': 'адекватно', 'next_q_str': 'nervous_06'},
                {'q_str': 'nervous_05', 'ans': 'остро', 'next_q_str': 'nervous_06'},
                {'q_str': 'nervous_05', 'ans': 'только с поддержкой препаратов', 'next_q_str': 'nervous_06'},
                {'q_str': 'nervous_06', 'ans': 'да', 'next_q_str': 'nervous_07'},
                {'q_str': 'nervous_06', 'ans': 'нет', 'next_q_str': 'nervous_07'},
                {'q_str': 'nervous_07', 'ans': 'легко', 'next_q_str': 'nervous_08'},
                {'q_str': 'nervous_07', 'ans': 'сложно', 'next_q_str': 'nervous_08'},
                {'q_str': 'nervous_07', 'ans': 'зависит от ситуации', 'next_q_str': 'nervous_08'},
                {'q_str': 'nervous_08', 'ans': 'да', 'next_q_str': 'anemia_01'},
                {'q_str': 'nervous_08', 'ans': 'кажется, снижается', 'next_q_str': 'anemia_01'},
                {'q_str': 'nervous_08', 'ans': 'не устраивает', 'next_q_str': 'anemia_01'},

                # ANEMIA BLOCK Logic
                {'q_str': 'anemia_01', 'ans': 'да', 'next_q_str': 'anemia_02'},
                {'q_str': 'anemia_01', 'ans': 'нет', 'next_q_str': 'anemia_02'},
                {'q_str': 'anemia_02', 'ans': 'да', 'next_q_str': 'anemia_03'},
                {'q_str': 'anemia_02', 'ans': 'нет', 'next_q_str': 'anemia_03'},
                {'q_str': 'anemia_03', 'ans': 'да', 'next_q_str': 'anemia_04'},
                {'q_str': 'anemia_03', 'ans': 'нет', 'next_q_str': 'anemia_04'},
                {'q_str': 'anemia_04', 'ans': 'да', 'next_q_str': 'anemia_05'},
                {'q_str': 'anemia_04', 'ans': 'нет', 'next_q_str': 'anemia_05'},
                {'q_str': 'anemia_05', 'ans': 'да', 'next_q_str': 'anemia_06'},
                {'q_str': 'anemia_05', 'ans': 'нет', 'next_q_str': 'anemia_06'},
                {'q_str': 'anemia_06', 'ans': 'да', 'next_q_str': 'anemia_07'},
                {'q_str': 'anemia_06', 'ans': 'нет', 'next_q_str': 'anemia_07'},
                {'q_str': 'anemia_07', 'ans': 'да', 'next_q_str': 'anemia_08'},
                {'q_str': 'anemia_07', 'ans': 'нет', 'next_q_str': 'anemia_08'},
                {'q_str': 'anemia_08', 'ans': 'нет', 'next_q_str': 'oda_01'}, # For males, go to ODA block
                {'q_str': 'anemia_08', 'ans': 'иногда', 'next_q_str': 'oda_01'},
                {'q_str': 'anemia_08', 'ans': 'часто', 'next_q_str': 'oda_01'},

                # FEMALE BLOCK Logic
                {'q_str': 'female_01', 'ans': 'любой', 'next_q_str': 'female_02'},
                {'q_str': 'female_02', 'ans': 'регулярный цикл', 'next_q_str': 'female_03'},
                {'q_str': 'female_02', 'ans': 'нерегулярный цикл', 'next_q_str': 'female_03'},
                {'q_str': 'female_02', 'ans': 'беременность / ГВ', 'next_q_str': 'female_03'},
                {'q_str': 'female_02', 'ans': 'менопауза', 'next_q_str': 'female_03'},
                {'q_str': 'female_03', 'ans': 'да', 'next_q_str': 'female_04'},
                {'q_str': 'female_03', 'ans': 'нет', 'next_q_str': 'female_04'},
                {'q_str': 'female_04', 'ans': 'любой', 'next_q_str': 'female_05'},
                {'q_str': 'female_05', 'ans': '≤3 дней', 'next_q_str': 'female_06'},
                {'q_str': 'female_05', 'ans': '3–4 дня', 'next_q_str': 'female_06'},
                {'q_str': 'female_05', 'ans': '5–6 дней', 'next_q_str': 'female_06'},
                {'q_str': 'female_05', 'ans': 'более 6 дней', 'next_q_str': 'female_06'},
                {'q_str': 'female_06', 'ans': 'любой', 'next_q_str': 'female_07'},
                {'q_str': 'female_07', 'ans': 'да', 'next_q_str': 'female_08'},
                {'q_str': 'female_07', 'ans': 'нет', 'next_q_str': 'female_08'},
                {'q_str': 'female_07', 'ans': 'иногда', 'next_q_str': 'female_08'},
                {'q_str': 'female_08', 'ans': 'любой', 'next_q_str': 'female_09'},
                {'q_str': 'female_09', 'ans': 'любой', 'next_q_str': 'female_10'},
                {'q_str': 'female_10', 'ans': 'красные без сгустков', 'next_q_str': 'female_11'},
                {'q_str': 'female_10', 'ans': 'темные со сгустками', 'next_q_str': 'female_11'},
                {'q_str': 'female_10', 'ans': 'темные без сгустков', 'next_q_str': 'female_11'},
                {'q_str': 'female_10', 'ans': 'мажущие', 'next_q_str': 'female_11'},
                {'q_str': 'female_11', 'ans': 'мажущие', 'next_q_str': 'female_12'},
                {'q_str': 'female_11', 'ans': 'обильные', 'next_q_str': 'female_12'},
                {'q_str': 'female_11', 'ans': 'нет', 'next_q_str': 'female_12'},
                {'q_str': 'female_12', 'ans': 'да', 'next_q_str': 'female_13'},
                {'q_str': 'female_12', 'ans': 'нет', 'next_q_str': 'female_13'},
                {'q_str': 'female_13', 'ans': 'да', 'next_q_str': 'oda_01'},
                {'q_str': 'female_13', 'ans': 'нет', 'next_q_str': 'oda_01'},

                # ODA BLOCK Logic
                {'q_str': 'oda_01', 'ans': 'любой', 'next_q_str': 'oda_02'},
                {'q_str': 'oda_02', 'ans': 'любой', 'next_q_str': 'oda_03'},
                {'q_str': 'oda_03', 'ans': 'любой', 'next_q_str': 'oda_04'},
                {'q_str': 'oda_04', 'ans': 'да', 'next_q_str': 'oda_05'},
                {'q_str': 'oda_04', 'ans': 'нет', 'next_q_str': 'oda_05'},
                {'q_str': 'oda_05', 'ans': 'да', 'next_q_str': 'oda_06'},
                {'q_str': 'oda_05', 'ans': 'нет', 'next_q_str': 'oda_06'},
                {'q_str': 'oda_06', 'ans': 'нет', 'next_q_str': 'oda_07'},
                {'q_str': 'oda_06', 'ans': 'больше на 1–2 размера', 'next_q_str': 'oda_07'},
                {'q_str': 'oda_06', 'ans': 'сложно подобрать обувь', 'next_q_str': 'oda_07'},
                {'q_str': 'oda_07', 'ans': 'любой', 'next_q_str': 'final_end'}
            ]
            
            for logic_def in logic_definitions:
                question_id = question_id_map[logic_def['q_str']]
                next_question_id = None
                if logic_def['next_q_str'] and logic_def['next_q_str'] != 'конец опросника':
                    next_question_id = question_id_map[logic_def['next_q_str']]
                
                session.add(QuestionLogic(
                    question_id=question_id,
                    answer_value=logic_def['ans'],
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
    await init_db() # Call init_db in polling mode as well
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