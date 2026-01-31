import asyncio
import logging
import sys
import datetime
import json

# Configure logging first
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from aiogram import Bot, Dispatcher, types # Added types here
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
        # Seed questionnaire if empty
        if (await session.execute(select(Questionnaire))).scalar_one_or_none() is None:
            logging.info("Seeding new questionnaire data...")
            main_questionnaire = Questionnaire(title="Основной опросник")
            session.add(main_questionnaire)
            await session.flush()

            # --- Map of string IDs to Question objects for easy linking ---
            questions_to_add = []
            logic_to_add = []
            
            # --- Gender Selection (Initial Question) ---
            q_gender = Question(questionnaire_id=main_questionnaire.id, text="Пожалуйста, укажите ваш пол:", type="single")
            questions_to_add.append(q_gender)
            await session.flush() # To get q_gender.id

            # Helper to map string IDs to actual Question objects after they are added
            question_id_map = {}
            current_question_id_counter = q_gender.id # Start counter from here

            def get_question_id_by_string_id(string_id: str):
                nonlocal current_question_id_counter
                if string_id not in question_id_map:
                    current_question_id_counter += 1
                    question_id_map[string_id] = current_question_id_counter
                return question_id_map[string_id]

            # --- Helper to create Question and get its ID ---
            def create_question(string_id, text, q_type, allow_photo=False):
                q_id = get_question_id_by_string_id(string_id)
                q = Question(id=q_id, questionnaire_id=main_questionnaire.id, text=text, type=q_type, allow_photo=allow_photo)
                questions_to_add.append(q)
                return q_id

            # --- Helper to create QuestionLogic ---
            def create_logic(question_string_id, answer_value, next_question_string_id):
                current_q_id = get_question_id_by_string_id(question_string_id)
                next_q_id = None
                if next_question_string_id and next_question_string_id != "конец опросника":
                    next_q_id = get_question_id_by_string_id(next_question_string_id)
                logic_to_add.append(QuestionLogic(question_id=current_q_id, answer_value=answer_value, next_question_id=next_q_id))
            
            # Manually map q_gender to its id as it's the first one
            question_id_map['gender_selection'] = q_gender.id

            # --- Questions Definition ---
            # GENERAL BLOCK
            create_question('general_01', 'Ваш род занятий, работа', 'multi')
            create_question('general_02', 'Присутствуют ли в вашей жизни спорт и физическая активность?', 'single')
            create_question('general_03', 'Если у вас есть или были хронические / наследственные заболевания — укажите какие', 'text')
            create_question('general_04', 'Есть ли хронические / генетические заболевания у ваших близких родственников?', 'text')
            create_question('general_05', 'Были ли у вас операции? Какие и как давно?', 'text')
            create_question('general_06', 'Принимаете ли вы на постоянной основе фармпрепараты или БАДы? Если да — какие', 'text')
            create_question('general_07', 'Испытываете ли вы симптомы аллергии?', 'single')
            create_question('general_08', 'Как часто вы переносите сезонные ОРВИ?', 'single')
            create_question('general_09', 'Кратко опишите ваш режим дня (сон, работа, питание, транспорт, прогулки, хобби)', 'text')
            create_question('general_10', 'Оцените качество вашего сна', 'multi')
            create_question('general_11', 'Знакомы ли вы с правилами гигиены сна?', 'single')
            create_question('general_12', 'Бывают ли у вас мышечные судороги, спазмы, онемение?', 'multi')
            create_question('general_13', 'Испытываете ли вы головокружение?', 'single')
            create_question('general_14', 'Знаете ли вы своё артериальное давление и пульс?', 'single')
            create_question('general_15', 'Беспокоят ли вас отеки?', 'multi')
            create_question('general_16', 'Бывают ли частые или ночные позывы к мочеиспусканию?', 'single')
            create_question('general_17', 'Беспокоят ли вас вены, варикоз, тяжесть в ногах?', 'single')
            create_question('general_18', 'Оцените ваш питьевой режим', 'single')
            create_question('general_19', 'Устраивает ли вас состояние кожи, волос и ногтей?', 'single')
            create_question('general_20', 'Беспокоит ли вас запах изо рта, стоматологические или ЛОР-проблемы?', 'single')
            create_question('general_21', 'Были ли у вас ортодонтические патологии?', 'single')
            create_question('general_22', 'Оцените потоотделение', 'single')
            create_question('general_23', 'Есть ли у вас зависимости?', 'multi')
            create_question('general_24', 'Оцените уровень стресса по шкале от 1 до 10', 'single')
            create_question('general_25', 'Есть ли проблемы опорно-двигательного аппарата?', 'single')
            create_question('general_26', 'Были ли серьезные травмы опорно-двигательного аппарата?', 'single')
            create_question('general_27', 'Оцените уровень либидо', 'single')
            create_question('general_28', 'Считаете ли вы ваше питание полноценным?', 'single')
            create_question('general_29', 'Испытываете ли вы трудности с запоминанием информации?', 'single')

            # GKT BLOCK
            create_question('gkt_01', 'Испытываете ли вы болевые ощущения или дискомфорт в животе?', 'multi')
            create_question('gkt_02', 'Связаны ли боли с приемом пищи?', 'single')
            create_question('gkt_03', 'Беспокоят ли изжога, жжение за грудиной, отрыжка, нарушение глотания?', 'single')
            create_question('gkt_04', 'Бывает ли вздутие живота, метеоризм?', 'single')
            create_question('gkt_05', 'Оцените ваш аппетит', 'single')
            create_question('gkt_06', 'Какая регулярность стула?', 'single')
            create_question('gkt_07', 'Оцените характер стула', 'single')
            create_question('gkt_08', 'Испытываете ли вы тошноту?', 'multi')
            create_question('gkt_09', 'Как переносите пропуск приема пищи?', 'single')
            create_question('gkt_10', 'Бывает ли сонливость или упадок энергии после еды?', 'single')
            create_question('gkt_11', 'Есть ли продукты, после которых вам становится хуже?', 'single')

            # SKIN BLOCK
            create_question('skin_01', 'Что вас не устраивает в состоянии кожи?', 'multi')
            create_question('skin_02', 'Обращались ли вы к специалисту по поводу кожи?', 'single')

            # NERVOUS SYSTEM BLOCK
            create_question('nervous_01', 'Как вы оцениваете свою память?', 'multi')
            create_question('nervous_02', 'Бывают ли тики, непроизвольные движения?', 'single')
            create_question('nervous_03', 'Как вы чувствуете себя в общении?', 'single')
            create_question('nervous_04', 'Вас устраивает ваше эмоциональное состояние?', 'single')
            create_question('nervous_05', 'Как вы реагируете на стресс?', 'single')
            create_question('nervous_06', 'Есть ли у вас навыки стресс-менеджмента?', 'single')
            create_question('nervous_07', 'Как вы принимаете решения?', 'single')
            create_question('nervous_08', 'Устраивает ли вас умственная работоспособность?', 'single')

            # ANEMIA BLOCK
            create_question('anemia_01', 'Беспокоит ли вас слабость, быстрая утомляемость?', 'single')
            create_question('anemia_02', 'Есть ли бледность кожи, выпадение волос?', 'single')
            create_question('anemia_03', 'Бывают ли необычные вкусовые желания (мел, лед и т.п.)?', 'single')
            create_question('anemia_04', 'Есть ли одышка или сердцебиение при легкой нагрузке?', 'single')
            create_question('anemia_05', 'Тянет ли вас к запахам (лак, бензин и т.п.)?', 'single')
            create_question('anemia_06', 'Бывают ли заеды в уголках рта?', 'single')
            create_question('anemia_07', 'Есть ли отвращение к мясу или продуктам?', 'single')
            create_question('anemia_08', 'Ощущаете ли зябкость рук и ног?', 'single')

            # FEMALE BLOCK
            create_question('female_01', 'Укажите возраст первой менструации (менархе)', 'text')
            create_question('female_02', 'Сейчас у вас:', 'single')
            create_question('female_03', 'Были ли беременности или роды?', 'single')
            create_question('female_04', 'Продолжительность цикла (в днях)', 'text')
            create_question('female_05', 'Продолжительность менструации', 'single')
            create_question('female_06', 'Есть ли симптомы ПМС?', 'multi')
            create_question('female_07', 'Бывают ли проблемы со сном в период менструации?', 'single')
            create_question('female_08', 'Оцените обильность выделений (1–10)', 'single')
            create_question('female_09', 'Оцените болезненность (1–10)', 'single')
            create_question('female_10', 'Характер выделений', 'single')
            create_question('female_11', 'Есть ли межменструальные кровянистые выделения?', 'single')
            create_question('female_12', 'Бывают ли проявления цистита?', 'single')
            create_question('female_13', 'Беспокоят ли симптомы молочницы / дисбиоза?', 'single')

            # ODA BLOCK
            create_question('oda_01', 'Где вас беспокоят боли?', 'multi')
            create_question('oda_02', 'Оцените интенсивность боли (1–10)', 'single')
            create_question('oda_03', 'Есть ли скованность суставов?', 'multi')
            create_question('oda_04', 'Есть ли диагностированные заболевания ОДА?', 'single')
            create_question('oda_05', 'Есть ли патологии стопы?', 'single')
            create_question('oda_06', 'Изменился ли размер обуви?', 'single')
            create_question('oda_07', 'Обращались ли вы к специалистам?', 'multi')

            # FINAL
            create_question('final_end', 'Спасибо за заполнение опросника. Мы проанализируем данные и свяжемся с вами.', 'text')
            
            # --- Logic Definition ---
            # Gender Selection Logic
            create_logic('gender_selection', 'Мужской', 'general_01')
            create_logic('gender_selection', 'Женский', 'female_01')

            # GENERAL BLOCK Logic
            create_logic('general_01', 'любой', 'general_02') # multi-choice "any" transitions
            create_logic('general_02', 'да, регулярно', 'general_03')
            create_logic('general_02', 'нерегулярно, время от времени', 'general_03')
            create_logic('general_02', 'нет и не было', 'general_03')
            create_logic('general_02', 'я профессиональный спортсмен', 'general_03')
            create_logic('general_03', 'любой', 'general_04')
            create_logic('general_04', 'любой', 'general_05')
            create_logic('general_05', 'любой', 'general_06')
            create_logic('general_06', 'любой', 'general_07')
            create_logic('general_07', 'очень часто', 'general_08')
            create_logic('general_07', 'иногда', 'general_08')
            create_logic('general_07', 'сезонно', 'general_08')
            create_logic('general_07', 'нет', 'general_08')
            create_logic('general_08', 'очень редко', 'general_09')
            create_logic('general_08', '1–2 раза в год', 'general_09')
            create_logic('general_08', '3–4 раза в год', 'anemia_01')
            create_logic('general_08', 'постоянно, даже летом', 'anemia_01')
            create_logic('general_09', 'любой', 'general_10')
            create_logic('general_10', 'любой', 'general_11') # multi-choice "any" transitions
            create_logic('general_11', 'да, стараюсь придерживаться', 'general_12')
            create_logic('general_11', 'да, но не получается соблюдать', 'general_12')
            create_logic('general_11', 'нет, не знаком', 'general_12')
            create_logic('general_12', 'любой', 'general_13') # multi-choice "any" transitions
            create_logic('general_13', 'да, часто', 'nervous_01')
            create_logic('general_13', 'иногда', 'nervous_01')
            create_logic('general_13', 'нет', 'general_14')
            create_logic('general_14', 'не знаю', 'general_15')
            create_logic('general_14', 'повышенное / гипертония', 'general_15')
            create_logic('general_14', 'пониженное', 'anemia_01')
            create_logic('general_14', 'нестабильное', 'anemia_01')
            create_logic('general_14', 'есть трекер', 'general_15')
            create_logic('general_15', 'любой', 'general_16') # multi-choice "any" transitions
            create_logic('general_16', 'да', 'general_17')
            create_logic('general_16', 'иногда', 'general_17')
            create_logic('general_16', 'нет', 'general_17')
            create_logic('general_17', 'нет', 'general_18')
            create_logic('general_17', 'часто', 'general_18')
            create_logic('general_17', 'иногда', 'general_18')
            create_logic('general_18', 'пью воду адекватно', 'general_19')
            create_logic('general_18', 'воду не люблю, но пью другие напитки', 'general_19')
            create_logic('general_18', 'забываю пить', 'general_19')
            create_logic('general_18', 'не чувствую жажды', 'general_19')
            create_logic('general_18', 'пью много, жажду сложно утолить', 'general_19')
            create_logic('general_19', 'да, всё хорошо', 'general_20')
            create_logic('general_19', 'есть проблемы с кожей', 'skin_01')
            create_logic('general_19', 'не устраивает состояние волос / ногтей', 'anemia_01')
            create_logic('general_20', 'да', 'general_21')
            create_logic('general_20', 'нет', 'general_21')
            create_logic('general_21', 'да', 'general_22')
            create_logic('general_21', 'сейчас прохожу лечение', 'general_22')
            create_logic('general_21', 'уже исправлены', 'general_22')
            create_logic('general_21', 'нет', 'general_22')
            create_logic('general_22', 'сильное с запахом', 'general_23')
            create_logic('general_22', 'сильное без запаха', 'general_23')
            create_logic('general_22', 'нормальное', 'general_23')
            create_logic('general_22', 'слабое', 'general_23')
            create_logic('general_23', 'нет', 'general_24')
            create_logic('general_23', 'любой', 'nervous_01') # any(except "нет") -> nervous_01
            create_logic('general_24', '7–10', 'nervous_01')
            create_logic('general_24', '1–6', 'general_25')
            create_logic('general_25', 'да', 'oda_01')
            create_logic('general_25', 'сейчас нет', 'general_26')
            create_logic('general_25', 'нет', 'general_26')
            create_logic('general_26', 'да', 'general_27')
            create_logic('general_26', 'нет', 'general_27')
            create_logic('general_27', 'всё отлично', 'general_28')
            create_logic('general_27', 'устраивает', 'general_28')
            create_logic('general_27', 'наблюдаю снижение', 'general_28')
            create_logic('general_27', 'не могу оценить', 'general_28')
            create_logic('general_27', 'пропустить', 'general_28')
            create_logic('general_28', 'нет', 'general_29')
            create_logic('general_28', 'да, считаю КБЖУ', 'general_29')
            create_logic('general_28', 'соблюдаю протокол питания', 'general_29')
            create_logic('general_28', 'стараюсь следить за качеством', 'general_29')
            create_logic('general_29', 'да', 'nervous_01')
            create_logic('general_29', 'нет', 'gkt_01')
            
            # GKT BLOCK Logic
            create_logic('gkt_01', 'нет', 'gkt_03')
            create_logic('gkt_01', 'любой', 'gkt_02') # any(except "нет") -> gkt_02
            create_logic('gkt_02', 'сразу после еды', 'gkt_03')
            create_logic('gkt_02', 'через 1–2 часа', 'gkt_03')
            create_logic('gkt_02', 'связаны с голодом', 'gkt_03')
            create_logic('gkt_02', 'не связаны', 'gkt_03')
            create_logic('gkt_02', 'бывает по-разному', 'gkt_03')
            create_logic('gkt_03', 'часто', 'gkt_04')
            create_logic('gkt_03', 'иногда', 'gkt_04')
            create_logic('gkt_03', 'нет', 'gkt_04')
            create_logic('gkt_04', 'нет', 'gkt_05')
            create_logic('gkt_04', 'иногда', 'gkt_05')
            create_logic('gkt_04', 'постоянно', 'gkt_05')
            create_logic('gkt_05', 'стабильный, хороший', 'gkt_06')
            create_logic('gkt_05', 'постоянно хочется есть', 'gkt_06')
            create_logic('gkt_05', 'плохой', 'gkt_06')
            create_logic('gkt_05', 'нестабильный', 'gkt_06')
            create_logic('gkt_06', 'ежедневно утром', 'gkt_07')
            create_logic('gkt_06', 'ежедневно в разное время', 'gkt_07')
            create_logic('gkt_06', 'несколько раз в день', 'gkt_07')
            create_logic('gkt_06', 'непредсказуемый', 'gkt_07')
            create_logic('gkt_06', 'не каждый день', 'gkt_07')
            create_logic('gkt_07', 'нормальный', 'gkt_08')
            create_logic('gkt_07', 'склонность к диарее', 'gkt_08')
            create_logic('gkt_07', 'плотный, сухой', 'gkt_08')
            create_logic('gkt_07', 'нестабильный', 'gkt_08')
            create_logic('gkt_07', 'есть примеси', 'gkt_08')
            create_logic('gkt_08', 'любой', 'gkt_09') # multi-choice "any" transitions
            create_logic('gkt_09', 'нормально', 'gkt_10')
            create_logic('gkt_09', 'головокружение, слабость', 'gkt_10')
            create_logic('gkt_09', 'очень плохо', 'gkt_10')
            create_logic('gkt_10', 'да', 'gkt_11')
            create_logic('gkt_10', 'нет', 'gkt_11')
            create_logic('gkt_10', 'редко после обильной еды', 'gkt_11')
            create_logic('gkt_11', 'да', 'skin_01')
            create_logic('gkt_11', 'нет', 'skin_01')

            # SKIN BLOCK Logic
            create_logic('skin_01', 'любой', 'skin_02') # multi-choice "any" transitions
            create_logic('skin_02', 'да', 'nervous_01')
            create_logic('skin_02', 'нет', 'nervous_01')
            create_logic('skin_02', 'постоянно наблюдаюсь', 'nervous_01')

            # NERVOUS SYSTEM BLOCK Logic
            create_logic('nervous_01', 'любой', 'nervous_02') # multi-choice "any" transitions
            create_logic('nervous_02', 'да', 'nervous_03')
            create_logic('nervous_02', 'иногда', 'nervous_03')
            create_logic('nervous_02', 'нет', 'nervous_03')
            create_logic('nervous_03', 'легко общаюсь', 'nervous_04')
            create_logic('nervous_03', 'быстро устаю', 'nervous_04')
            create_logic('nervous_03', 'комфортно одному', 'nervous_04')
            create_logic('nervous_03', 'не могу без общения', 'nervous_04')
            create_logic('nervous_04', 'да', 'nervous_05')
            create_logic('nervous_04', 'нет', 'nervous_05')
            create_logic('nervous_04', 'наблюдаюсь у психотерапевта', 'nervous_05')
            create_logic('nervous_05', 'адекватно', 'nervous_06')
            create_logic('nervous_05', 'остро', 'nervous_06')
            create_logic('nervous_05', 'только с поддержкой препаратов', 'nervous_06')
            create_logic('nervous_06', 'да', 'nervous_07')
            create_logic('nervous_06', 'нет', 'nervous_07')
            create_logic('nervous_07', 'легко', 'nervous_08')
            create_logic('nervous_07', 'сложно', 'nervous_08')
            create_logic('nervous_07', 'зависит от ситуации', 'nervous_08')
            create_logic('nervous_08', 'да', 'anemia_01')
            create_logic('nervous_08', 'кажется, снижается', 'anemia_01')
            create_logic('nervous_08', 'не устраивает', 'anemia_01')

            # ANEMIA BLOCK Logic
            create_logic('anemia_01', 'да', 'anemia_02')
            create_logic('anemia_01', 'нет', 'anemia_02')
            create_logic('anemia_02', 'да', 'anemia_03')
            create_logic('anemia_02', 'нет', 'anemia_03')
            create_logic('anemia_03', 'да', 'anemia_04')
            create_logic('anemia_03', 'нет', 'anemia_04')
            create_logic('anemia_04', 'да', 'anemia_05')
            create_logic('anemia_04', 'нет', 'anemia_05')
            create_logic('anemia_05', 'да', 'anemia_06')
            create_logic('anemia_05', 'нет', 'anemia_06')
            create_logic('anemia_06', 'да', 'anemia_07')
            create_logic('anemia_06', 'нет', 'anemia_07')
            create_logic('anemia_07', 'да', 'anemia_08')
            create_logic('anemia_07', 'нет', 'anemia_08')
            create_logic('anemia_08', 'нет', 'female_01') # For females, go to female block
            create_logic('anemia_08', 'иногда', 'female_01')
            create_logic('anemia_08', 'часто', 'female_01')

            # FEMALE BLOCK Logic
            create_logic('female_01', 'любой', 'female_02')
            create_logic('female_02', 'регулярный цикл', 'female_03')
            create_logic('female_02', 'нерегулярный цикл', 'female_03')
            create_logic('female_02', 'беременность / ГВ', 'female_03')
            create_logic('female_02', 'менопауза', 'female_03')
            create_logic('female_03', 'да', 'female_04')
            create_logic('female_03', 'нет', 'female_04')
            create_logic('female_04', 'любой', 'female_05')
            create_logic('female_05', '≤3 дней', 'female_06')
            create_logic('female_05', '3–4 дня', 'female_06')
            create_logic('female_05', '5–6 дней', 'female_06')
            create_logic('female_05', 'более 6 дней', 'female_06')
            create_logic('female_06', 'любой', 'female_07') # multi-choice "any" transitions
            create_logic('female_07', 'да', 'female_08')
            create_logic('female_07', 'нет', 'female_08')
            create_logic('female_07', 'иногда', 'female_08')
            create_logic('female_08', 'любой', 'female_09') # single-choice number
            create_logic('female_09', 'любой', 'female_10') # single-choice number
            create_logic('female_10', 'красные без сгустков', 'female_11')
            create_logic('female_10', 'темные со сгустками', 'female_11')
            create_logic('female_10', 'темные без сгустков', 'female_11')
            create_logic('female_10', 'мажущие', 'female_11')
            create_logic('female_11', 'мажущие', 'female_12')
            create_logic('female_11', 'обильные', 'female_12')
            create_logic('female_11', 'нет', 'female_12')
            create_logic('female_12', 'да', 'female_13')
            create_logic('female_12', 'нет', 'female_13')
            create_logic('female_13', 'да', 'oda_01')
            create_logic('female_13', 'нет', 'oda_01')

            # ODA BLOCK Logic
            create_logic('oda_01', 'любой', 'oda_02') # multi-choice "any" transitions
            create_logic('oda_02', 'любой', 'oda_03') # single-choice number
            create_logic('oda_03', 'любой', 'oda_04') # multi-choice "any" transitions
            create_logic('oda_04', 'да', 'oda_05')
            create_logic('oda_04', 'нет', 'oda_05')
            create_logic('oda_05', 'да', 'oda_06')
            create_logic('oda_05', 'нет', 'oda_06')
            create_logic('oda_06', 'нет', 'oda_07')
            create_logic('oda_06', 'больше на 1–2 размера', 'oda_07')
            create_logic('oda_06', 'сложно подобрать обувь', 'oda_07')
            create_logic('oda_07', 'любой', 'final_end') # multi-choice "any" transitions

            # Final END
            create_logic('final_end', 'любой', 'конец опросника') # This signifies the end of the questionnaire
            
            await session.commit()
            logging.info("Questionnaire data seeded.")
        
    logging.info("Database initialization complete.")


async def on_startup_webhook(bot: Bot):
    await init_db()
    webhook_url = f"{settings.WEBHOOK_HOST}{settings.WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)
    logging.info(f"Telegram Webhook set to {webhook_url}")

    if settings.YOOKASSA_NOTIFICATION_URL:
        # We need to explicitly set the webhook URL for YooKassa
        # However, this is done by setting Configuration.webhook_url in YooKassaService __init__
        # So we just log it here.
        logging.info(f"YooKassa Notifications expected at: {settings.YOOKASSA_NOTIFICATION_URL}")


async def on_shutdown_webhook(bot: Bot):
    logging.info("Shutting down and deleting Telegram webhook...")
    await bot.delete_webhook()
    logging.info("Telegram Webhook deleted.")


async def start_polling(dp: Dispatcher, bot: Bot):
    logging.info("Starting bot in polling mode...")
    dp.startup.register(init_db)
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
            from urllib.parse import urlparse
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
