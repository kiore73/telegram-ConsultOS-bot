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


import aiofiles
...
async def seed_database(session):
    logging.info("Seeding database with new structure...")

    logging.info("Seeding 'basic' questionnaire...")
    basic_questionnaire = Questionnaire(title="basic")
    session.add(basic_questionnaire)
    await session.flush()

    options_data_basic = {
        'q_gender': ['Мужчина', 'Женщина'],
        'q_occupation': ['Сидячая', 'Присутствует физическая нагрузка', 'Высокая умственная нагрузка / высокий уровень ответственности', 'Приходится долго стоять', 'Много разъездов, поездок, перелетов'],
        'q_sport_activity': ['Да, регулярно', 'Нерегулярно, время от времени', 'Нет и не было', 'Я профессиональный спортсмен'],
        'q_allergy': ['Очень часто', 'Иногда', 'Сезонно', 'Нет'],
        'q_orvi': ['Очень редко', '1–2 раза в год', '3–4 раза в год', 'Постоянно, даже летом'],
        'q_sleep_quality': ['Быстро засыпаю', 'Требуется более 40 минут для засыпания', 'Сон без пробуждений', 'Сон чуткий, есть пробуждения', 'Есть трекер сна', 'Просыпаюсь легко и чувствую восстановление', 'Просыпаюсь тяжело, но потом бодр', 'Тяжело проснуться, нет сил до обеда'],
        'q_sleep_hygiene': ['Да, стараюсь придерживаться', 'Да, но не получается соблюдать', 'Нет, не знаком'],
        'q_muscle_symptoms': ['Нет', 'Судороги ног ночью', 'Спазмы мышц шеи', 'Судороги или спазмы регулярно', 'Онемение конечностей'],
        'q_dizziness': ['Да', 'часто', 'Иногда', 'Нет'],
        'q_pressure': ['Не знаю', 'Повышенное / гипертония', 'Пониженное', 'Нестабильное', 'Есть трекер'],
        'q_edema': ['Нет', 'Постоянно', 'Летом', 'отекают ноги/лодыжки', 'Лицо и руки'],
        'q_urination': ['Да', 'Иногда', 'Нет'],
        'q_veins': ['Нет', 'беспокоит тяжесть', 'Часто'],
        'q_water': ['Пью достаточно воды', 'Воду не люблю, пью другие напитки', 'Забываю пить, часто жажда', 'Не чувствую жажды', 'Пью много, жажда не утоляется'],
        'q_gut_pain': ['В верхней части живота (эпигастрий)', 'В области пупка', 'Внизу живота', 'Больше справа', 'Больше слева или в области спины', 'Нет'],
        'q_gut_pain_relation': ['Сразу после еды', 'В течение 1–2 часов', 'Связаны с голодом', 'Не связаны', 'Бывает по-разному'],
        'q_gut_heartburn': ['Часто', 'Иногда', 'Нет'],
        'q_gut_bloating': ['Нет', 'Иногда', 'Постоянно'],
        'q_gut_appetite': ['Стабильно хороший', 'Все время хочется есть', 'Плохой', 'Нестабильный'],
        'q_gut_stool_regular': ['Ежедневный по утрам', 'Ежедневный в разное время', 'Несколько раз в сутки', 'Непредсказуемый', 'Не каждый день'],
        'q_gut_stool_type': ['Нормальный, оформленный', 'Склонность к диарее', 'Очень плотный', 'Нестабильный', 'Есть примеси'],
        'q_gut_nausea': ['Бывает иногда', 'На определенные продукты', 'Очень редко', 'При укачивании'],
        'q_gut_hunger_break': ['Нормально', 'Появляется слабость, головокружение', 'Очень плохо'],
        'q_gut_sleep_after_food': ['Да', 'Нет', 'Бывает редко'],
        'q_gut_food_intolerance': ['Да', 'Нет'],
        'q_skin_issues': ['Сухость, раздражение', 'Изменение цвета', 'Высыпания, дерматиты', 'Акне', 'Повышенная жирность', 'Папилломы, родинки', 'Бородавки', 'Потеря упругости', 'Стрии', 'Зуд', 'Возрастные изменения', 'Отечность', 'Витилиго', 'Псориаз', 'Новообразования', 'Грибок'],
        'q_skin_doctor': ['Да', 'Нет', 'Постоянно наблюдаюсь'],
        'q_nervous_problem_question': ['Да', 'Нет'],
        'q_nervous_memory': ['Все хорошо', 'Страдает кратковременная память', 'Плохо удерживаю информацию', 'Все забываю', 'Забываю слова и имена'],
        'q_nervous_tics': ['Да', 'Иногда', 'Нет'],
        'q_nervous_communication': ['Легко общаюсь', 'Устаю от общения', 'Предпочитаю одиночество', 'Не могу без общения'],
        'q_nervous_emotional': ['Да', 'Нет', 'Наблюдаюсь у специалиста'],
        'q_nervous_stress_reaction': ['Адекватно', 'Остро', 'С поддержкой препаратов'],
        'q_nervous_coping': ['Да', 'Нет'],
        'q_nervous_decisions': ['Легко', 'Сложно', 'Зависит от ситуации'],
        'q_nervous_thinking': ['Устраивает', 'Не устраивает'],
        'q_anemia_weakness': ['Да', 'Нет'],
        'q_anemia_skin': ['Да', 'Нет'],
        'q_anemia_taste': ['Да', 'Нет'],
        'q_anemia_breath': ['Да', 'Нет'],
        'q_anemia_smell': ['Да', 'Нет'],
        'q_anemia_cheilitis': ['Да', 'Нет'],
        'q_anemia_meat': ['Да', 'Нет'],
        'q_anemia_cold': ['Да', 'Нет'],
        'q_oda_pain': ['Голова', 'Шея', 'Спина', 'Поясница', 'Суставы'],
        'q_oda_pain_level': [],
        'q_oda_stiffness': ['Да', 'Нет'],
        'q_oda_diagnosis': ['Да', 'Нет'],
        'q_oda_feet': ['Да', 'Нет'],
        'q_oda_shoes': ['Да', 'Нет'],
        'q_oda_doctor': ['Да', 'Нет'],
        'q_women_menarche': [],
        'q_women_cycle_status': ['Регулярный', 'Нерегулярный', 'Отсутствует', 'Менопауза', 'Беременность', 'Лактация'],
        'q_women_pregnancy': ['Да', 'Нет'],
        'q_women_cycle_length': [],
        'q_women_menses_length': ['1-2 дня', '3-5 дней', 'более 5 дней'],
        'q_women_pms': ['Раздражительность', 'Плаксивость', 'Боль внизу живота', 'Набухание молочных желез', 'Головная боль', 'Слабость', 'Отсутствует'],
        'q_women_sleep_menses': ['Да', 'Нет'],
        'q_women_flow_amount': [],
        'q_women_pain_level': [],
        'q_women_flow_type': ['Обильные', 'Умеренные', 'Скудные'],
        'q_women_gut_menses': ['Да', 'Нет'],
        'q_women_bleeding_other_days': ['Да', 'Нет'],
        'q_women_cystitis': ['Да', 'Нет'],
        'q_women_candidiasis': ['Да', 'Нет'],
        'q_women_cosmetics_amount': ['3–4 и менее', '5–8', 'Около 10', 'Более 10'],
        'q_women_ecology': ['Да', 'Нет', 'Не в первую очередь'],
        'q_nervous_decisions': ['Легко', 'Сложно', 'Зависит от ситуации'], # This was duplicated in the original context, ensuring it's in options_data
        'q_nervous_thinking': ['Устраивает', 'Не устраивает'], # This was duplicated in the original context, ensuring it's in options_data
        'q_anemia_weakness': ['Да', 'Нет'], # Duplicated
        'q_anemia_skin': ['Да', 'Нет'], # Duplicated
        'q_anemia_taste': ['Да', 'Нет'], # Duplicated
        'q_anemia_breath': ['Да', 'Нет'], # Duplicated
        'q_anemia_smell': ['Да', 'Нет'], # Duplicated
        'q_anemia_cheilitis': ['Да', 'Нет'], # Duplicated
        'q_anemia_meat': ['Да', 'Нет'], # Duplicated
        'q_anemia_cold': ['Да', 'Нет'], # Duplicated
        'q_oda_stiffness': ['Да', 'Нет'], # Duplicated
        'q_oda_diagnosis': ['Да', 'Нет'], # Duplicated
        'q_oda_feet': ['Да', 'Нет'], # Duplicated
        'q_oda_shoes': ['Да', 'Нет'], # Duplicated
        'q_women_cycle_status': ['Регулярный', 'Нерегулярный', 'Отсутствует', 'Менопауза', 'Беременность', 'Лактация'], # Duplicated
        'q_women_pregnancy': ['Да', 'Нет'], # Duplicated
        'q_women_menses_length': ['1-2 дня', '3-5 дней', 'более 5 дней'], # Duplicated
        'q_women_sleep_menses': ['Да', 'Нет'], # Duplicated
        'q_women_flow_type': ['Обильные', 'Умеренные', 'Скудные'], # Duplicated
        'q_women_gut_menses': ['Да', 'Нет'], # Duplicated
        'q_women_bleeding_other_days': ['Да', 'Нет'], # Duplicated
        'q_women_cystitis': ['Да', 'Нет'], # Duplicated
        'q_women_candidiasis': ['Да', 'Нет'], # Duplicated
        'q_women_cosmetics_amount': ['3–4 и менее', '5–8', 'Около 10', 'Более 10'], # Duplicated
        'q_women_ecology': ['Да', 'Нет', 'Не в первую очередь'], # Duplicated
        'q_nervous_problem_question': ['Да', 'Нет'], # Duplicated
        'q_nervous_memory': ['Все хорошо', 'Страдает кратковременная память', 'Плохо удерживаю информацию', 'Все забываю', 'Забываю слова и имена'], # Duplicated
        'q_nervous_tics': ['Да', 'Иногда', 'Нет'], # Duplicated
        'q_nervous_communication': ['Легко общаюсь', 'Устаю от общения', 'Предпочитаю одиночество', 'Не могу без общения'], # Duplicated
        'q_nervous_emotional': ['Да', 'Нет', 'Наблюдаюсь у специалиста'], # Duplicated
        'q_nervous_stress_reaction': ['Адекватно', 'Остро', 'С поддержкой препаратов'], # Duplicated
        'q_nervous_coping': ['Да', 'Нет'], # Duplicated
    }
    
    question_definitions_basic = [
        {'id': 'q_gender', 'text': 'Укажите ваш пол', 'type': 'single'},
        {'id': 'q_occupation', 'text': 'Ваш род занятий, работа (можно выбрать несколько вариантов)', 'type': 'multi'},
        {'id': 'q_sport_activity', 'text': 'Присутствуют ли в вашей жизни спорт или физическая активность?', 'type': 'single'},
        {'id': 'q_chronic_diseases', 'text': 'Если у вас есть или были хронические или наследственные заболевания, укажите диагнозы', 'type': 'text'},
        {'id': 'q_family_diseases', 'text': 'Есть ли хронические или генетические заболевания у ваших ближайших биологических родственников?', 'type': 'text'},
        {'id': 'q_surgeries', 'text': 'Были ли у вас операции? Если да, какие и как давно?', 'type': 'text'},
        {'id': 'q_medications', 'text': 'Принимаете ли вы на постоянной основе фармацевтические препараты или БАДы? Если да, укажите какие', 'type': 'text'},
        {'id': 'q_allergy', 'text': 'Испытываете ли вы симптомы аллергии?', 'type': 'single'},
        {'id': 'q_orvi', 'text': 'Как часто вы переносите сезонные ОРВИ?', 'type': 'single'},
        {'id': 'q_daily_routine', 'text': 'Опишите кратко ваш режим дня (сон, питание, работа, транспорт, хобби, прогулки)', 'type': 'text'},
        {'id': 'q_sleep_quality', 'text': 'Оцените качество вашего сна (можно выбрать несколько вариантов)', 'type': 'multi'},
        {'id': 'q_sleep_hygiene', 'text': 'Знакомы ли вы с правилами и гигиеной здорового сна?', 'type': 'single'},
        {'id': 'q_muscle_symptoms', 'text': 'Наблюдали ли вы у себя мышечные судороги, слабость или онемение?', 'type': 'multi'},
        {'id': 'q_dizziness', 'text': 'Испытываете ли вы головокружение?', 'type': 'single'},
        {'id': 'q_pressure', 'text': 'Знаете ли вы свое артериальное давление и пульс?', 'type': 'single'},
        {'id': 'q_edema', 'text': 'Беспокоят ли вас отеки?', 'type': 'multi'},
        {'id': 'q_urination', 'text': 'Бывают ли стрессовые или ночные позывы к мочеиспусканию?', 'type': 'single'},
        {'id': 'q_veins', 'text': 'Беспокоят ли вас вены, сосудистые звездочки, варикоз, тяжесть в ногах?', 'type': 'single'},
        {'id': 'q_water', 'text': 'Оцените ваш питьевой режим', 'type': 'multi'},
        {'id': 'q_gut_pain', 'text': 'Испытываете ли вы болевые ощущения или дискомфорт в животе?', 'type': 'multi'},
        {'id': 'q_gut_pain_relation', 'text': 'Если есть боли, связаны ли они с приемом пищи?', 'type': 'single'},
        {'id': 'q_gut_heartburn', 'text': 'Беспокоят ли вас изжога, жжение за грудиной, отрыжка, нарушение глотания?', 'type': 'single'},
        {'id': 'q_gut_bloating', 'text': 'Беспокоят ли вас вздутие живота или метеоризм?', 'type': 'single'},
        {'id': 'q_gut_appetite', 'text': 'Оцените ваш аппетит', 'type': 'single'},
        {'id': 'q_gut_stool_regular', 'text': 'Какая регулярность стула?', 'type': 'single'},
        {'id': 'q_gut_stool_type', 'text': 'Оцените характер стула', 'type': 'single'},
        {'id': 'q_gut_nausea', 'text': 'Испытываете ли вы тошноту?', 'type': 'multi'},
        {'id': 'q_gut_hunger_break', 'text': 'Как вы переносите длительные перерывы между приемами пищи?', 'type': 'single'},
        {'id': 'q_gut_sleep_after_food', 'text': 'Испытываете ли вы сонливость после еды?', 'type': 'single'},
        {'id': 'q_gut_food_intolerance', 'text': 'Есть ли продукты, после которых вы замечаете ухудшение самочувствия?', 'type': 'single'},
        {'id': 'q_skin_issues', 'text': 'Что вас не устраивает в состоянии кожи? (можно выбрать несколько вариантов)', 'type': 'multi'},
        {'id': 'q_skin_doctor', 'text': 'Обращались ли вы к специалисту по поводу кожи?', 'type': 'single'},
        {'id': 'q_nervous_problem_question', 'text': 'Есть ли у вас проблемы с нервной системой или повышенный уровень стресса?', 'type': 'single'},
        {'id': 'q_nervous_memory', 'text': 'Как вы оцениваете свою память?', 'type': 'multi'},
        {'id': 'q_nervous_tics', 'text': 'Наблюдаете ли вы тики или непроизвольные движения?', 'type': 'single'},
        {'id': 'q_nervous_communication', 'text': 'Как вы ощущаете себя в общении с людьми?', 'type': 'single'},
        {'id': 'q_nervous_emotional', 'text': 'Устраивает ли вас ваше эмоциональное состояние?', 'type': 'single'},
        {'id': 'q_nervous_stress_reaction', 'text': 'Как вы реагируете на стресс?', 'type': 'single'},
        {'id': 'q_nervous_coping', 'text': 'Есть ли у вас навыки управления стрессом?', 'type': 'single'},
        {'id': 'q_nervous_decisions', 'text': 'Насколько легко вам принимать решения?', 'type': 'single'},
        {'id': 'q_nervous_thinking', 'text': 'Устраивает ли вас уровень мышления и умственной работоспособности?', 'type': 'single'},
        {'id': 'q_anemia_weakness', 'text': 'Беспокоит ли вас слабость или быстрая утомляемость?', 'type': 'single'},
        {'id': 'q_anemia_skin', 'text': 'Замечаете ли вы бледность кожи или выпадение волос?', 'type': 'single'},
        {'id': 'q_anemia_taste', 'text': 'Бывают ли необычные вкусовые желания (мел, лед и т.п.)?', 'type': 'single'},
        {'id': 'q_anemia_breath', 'text': 'Бывает ли одышка или учащенное сердцебиение при легкой нагрузке?', 'type': 'single'},
        {'id': 'q_anemia_smell', 'text': 'Есть ли тяга к необычным запахам (лак, бензин и т.п.)?', 'type': 'single'},
        {'id': 'q_anemia_cheilitis', 'text': 'Беспокоят ли заеды в углах рта?', 'type': 'single'},
        {'id': 'q_anemia_meat', 'text': 'Есть ли отвращение к мясу или продуктам?', 'type': 'single'},
        {'id': 'q_anemia_cold', 'text': 'Отмечаете ли повышенную зябкость рук и ног?', 'type': 'single'},
        {'id': 'q_oda_pain', 'text': 'Беспокоят ли вас болевые ощущения?', 'type': 'multi'},
        {'id': 'q_oda_pain_level', 'text': 'Оцените интенсивность боли по шкале от 1 до 10', 'type': 'text'},
        {'id': 'q_oda_stiffness', 'text': 'Есть ли скованность или тугоподвижность суставов?', 'type': 'single'},
        {'id': 'q_oda_diagnosis', 'text': 'Есть ли диагностированные заболевания ОДА (грыжи, артрит и т.п.)?', 'type': 'single'},
        {'id': 'q_oda_feet', 'text': 'Есть ли патологии стопы?', 'type': 'single'},
        {'id': 'q_oda_shoes', 'text': 'Изменился ли размер обуви?', 'type': 'single'},
        {'id': 'q_oda_doctor', 'text': 'Обращались ли вы к специалисту?', 'type': 'multi'},
        {'id': 'q_women_menarche', 'text': 'Укажите, по возможности, возраст начала первой менструации (менархе)', 'type': 'text'},
        {'id': 'q_women_cycle_status', 'text': 'Какое у вас текущее состояние менструального цикла?', 'type': 'single'},
        {'id': 'q_women_pregnancy', 'text': 'Были ли у вас беременности или роды?', 'type': 'single'},
        {'id': 'q_women_cycle_length', 'text': 'Укажите продолжительность цикла от первого дня менструации до последнего дня цикла (в днях)', 'type': 'text'},
        {'id': 'q_women_menses_length', 'text': 'Укажите среднюю продолжительность менструации', 'type': 'single'},
        {'id': 'q_women_pms', 'text': 'Беспокоят ли вас симптомы ПМС? (можно выбрать несколько вариантов)', 'type': 'multi'},
        {'id': 'q_women_sleep_menses', 'text': 'Замечаете ли вы проблемы со сном накануне или во время менструации?', 'type': 'single'},
        {'id': 'q_women_flow_amount', 'text': 'Оцените обильность менструальных выделений по шкале от 1 до 10', 'type': 'text'},
        {'id': 'q_women_pain_level', 'text': 'Оцените болезненность во время менструации по шкале от 1 до 10', 'type': 'text'},
        {'id': 'q_women_flow_type', 'text': 'Как вы можете описать менструальные выделения?', 'type': 'single'},
        {'id': 'q_women_gut_menses', 'text': 'Бывает ли дискомфорт со стороны ЖКТ во время или накануне менструации?', 'type': 'single'},
        {'id': 'q_women_bleeding_other_days', 'text': 'Бывают ли кровянистые выделения в другие дни цикла?', 'type': 'single'},
        {'id': 'q_women_cystitis', 'text': 'Бывают ли у вас проявления цистита?', 'type': 'single'},
        {'id': 'q_women_candidiasis': ['Да', 'Нет'],
        'q_women_cosmetics_amount': ['3–4 и менее', '5–8', 'Около 10', 'Более 10'],
        'q_women_ecology': ['Да', 'Нет', 'Не в первую очередь'],
        'q_survey_end': []
    }

    question_definitions_basic = [
        {'id': 'q_gender', 'text': 'Укажите ваш пол', 'type': 'single'},
        {'id': 'q_occupation', 'text': 'Ваш род занятий, работа (можно выбрать несколько вариантов)', 'type': 'multi'},
        {'id': 'q_sport_activity', 'text': 'Присутствуют ли в вашей жизни спорт или физическая активность?', 'type': 'single'},
        {'id': 'q_chronic_diseases', 'text': 'Если у вас есть или были хронические или наследственные заболевания, укажите диагнозы', 'type': 'text'},
        {'id': 'q_family_diseases', 'text': 'Есть ли хронические или генетические заболевания у ваших ближайших биологических родственников?', 'type': 'text'},
        {'id': 'q_surgeries', 'text': 'Были ли у вас операции? Если да, какие и как давно?', 'type': 'text'},
        {'id': 'q_medications', 'text': 'Принимаете ли вы на постоянной основе фармацевтические препараты или БАДы? Если да, укажите какие', 'type': 'text'},
        {'id': 'q_allergy', 'text': 'Испытываете ли вы симптомы аллергии?', 'type': 'single'},
        {'id': 'q_orvi', 'text': 'Как часто вы переносите сезонные ОРВИ?', 'type': 'single'},
        {'id': 'q_daily_routine', 'text': 'Опишите кратко ваш режим дня (сон, питание, работа, транспорт, хобби, прогулки)', 'type': 'text'},
        {'id': 'q_sleep_quality', 'text': 'Оцените качество вашего сна (можно выбрать несколько вариантов)', 'type': 'multi'},
        {'id': 'q_sleep_hygiene', 'text': 'Знакомы ли вы с правилами и гигиеной здорового сна?', 'type': 'single'},
        {'id': 'q_muscle_symptoms', 'text': 'Наблюдали ли вы у себя мышечные судороги, слабость или онемение?', 'type': 'multi'},
        {'id': 'q_dizziness', 'text': 'Испытываете ли вы головокружение?', 'type': 'single'},
        {'id': 'q_pressure', 'text': 'Знаете ли вы свое артериальное давление и пульс?', 'type': 'single'},
        {'id': 'q_edema', 'text': 'Беспокоят ли вас отеки?', 'type': 'multi'},
        {'id': 'q_urination', 'text': 'Бывают ли стрессовые или ночные позывы к мочеиспусканию?', 'type': 'single'},
        {'id': 'q_veins', 'text': 'Беспокоят ли вас вены, сосудистые звездочки, варикоз, тяжесть в ногах?', 'type': 'single'},
        {'id': 'q_water', 'text': 'Оцените ваш питьевой режим', 'type': 'multi'},
        {'id': 'q_gut_pain', 'text': 'Испытываете ли вы болевые ощущения или дискомфорт в животе?', 'type': 'multi'},
        {'id': 'q_gut_pain_relation', 'text': 'Если есть боли, связаны ли они с приемом пищи?', 'type': 'single'},
        {'id': 'q_gut_heartburn', 'text': 'Беспокоят ли вас изжога, жжение за грудиной, отрыжка, нарушение глотания?', 'type': 'single'},
        {'id': 'q_gut_bloating', 'text': 'Беспокоят ли вас вздутие живота или метеоризм?', 'type': 'single'},
        {'id': 'q_gut_appetite', 'text': 'Оцените ваш аппетит', 'type': 'single'},
        {'id': 'q_gut_stool_regular', 'text': 'Какая регулярность стула?', 'type': 'single'},
        {'id': 'q_gut_stool_type', 'text': 'Оцените характер стула', 'type': 'single'},
        {'id': 'q_gut_nausea', 'text': 'Испытываете ли вы тошноту?', 'type': 'multi'},
        {'id': 'q_gut_hunger_break', 'text': 'Как вы переносите длительные перерывы между приемами пищи?', 'type': 'single'},
        {'id': 'q_gut_sleep_after_food', 'text': 'Испытываете ли вы сонливость после еды?', 'type': 'single'},
        {'id': 'q_gut_food_intolerance', 'text': 'Есть ли продукты, после которых вы замечаете ухудшение самочувствия?', 'type': 'single'},
        {'id': 'q_skin_issues', 'text': 'Что вас не устраивает в состоянии кожи? (можно выбрать несколько вариантов)', 'type': 'multi'},
        {'id': 'q_skin_doctor', 'text': 'Обращались ли вы к специалисту по поводу кожи?', 'type': 'single'},
        {'id': 'q_nervous_problem_question', 'text': 'Есть ли у вас проблемы с нервной системой или повышенный уровень стресса?', 'type': 'single'},
        {'id': 'q_nervous_memory', 'text': 'Как вы оцениваете свою память?', 'type': 'multi'},
        {'id': 'q_nervous_tics', 'text': 'Наблюдаете ли вы тики или непроизвольные движения?', 'type': 'single'},
        {'id': 'q_nervous_communication', 'text': 'Как вы ощущаете себя в общении с людьми?', 'type': 'single'},
        {'id': 'q_nervous_emotional', 'text': 'Устраивает ли вас ваше эмоциональное состояние?', 'type': 'single'},
        {'id': 'q_nervous_stress_reaction', 'text': 'Как вы реагируете на стресс?', 'type': 'single'},
        {'id': 'q_nervous_coping', 'text': 'Есть ли у вас навыки управления стрессом?', 'type': 'single'},
        {'id': 'q_nervous_decisions', 'text': 'Насколько легко вам принимать решения?', 'type': 'single'},
        {'id': 'q_nervous_thinking', 'text': 'Устраивает ли вас уровень мышления и умственной работоспособности?', 'type': 'single'},
        {'id': 'q_anemia_weakness', 'text': 'Беспокоит ли вас слабость или быстрая утомляемость?', 'type': 'single'},
        {'id': 'q_anemia_skin', 'text': 'Замечаете ли вы бледность кожи или выпадение волос?', 'type': 'single'},
        {'id': 'q_anemia_taste', 'text': 'Бывают ли необычные вкусовые желания (мел, лед и т.п.)?', 'type': 'single'},
        {'id': 'q_anemia_breath', 'text': 'Бывает ли одышка или учащенное сердцебиение при легкой нагрузке?', 'type': 'single'},
        {'id': 'q_anemia_smell', 'text': 'Есть ли тяга к необычным запахам (лак, бензин и т.п.)?', 'type': 'single'},
        {'id': 'q_anemia_cheilitis', 'text': 'Беспокоят ли заеды в углах рта?', 'type': 'single'},
        {'id': 'q_anemia_meat', 'text': 'Есть ли отвращение к мясу или продуктам?', 'type': 'single'},
        {'id': 'q_anemia_cold', 'text': 'Отмечаете ли повышенную зябкость рук и ног?', 'type': 'single'},
        {'id': 'q_oda_pain', 'text': 'Беспокоят ли вас болевые ощущения?', 'type': 'multi'},
        {'id': 'q_oda_pain_level', 'text': 'Оцените интенсивность боли по шкале от 1 до 10', 'type': 'text'},
        {'id': 'q_oda_stiffness', 'text': 'Есть ли скованность или тугоподвижность суставов?', 'type': 'single'},
        {'id': 'q_oda_diagnosis', 'text': 'Есть ли диагностированные заболевания ОДА (грыжи, артрит и т.п.)?', 'type': 'single'},
        {'id': 'q_oda_feet', 'text': 'Есть ли патологии стопы?', 'type': 'single'},
        {'id': 'q_oda_shoes', 'text': 'Изменился ли размер обуви?', 'type': 'single'},
        {'id': 'q_oda_doctor', 'text': 'Обращались ли вы к специалисту?', 'type': 'multi'},
        {'id': 'q_women_menarche', 'text': 'Укажите, по возможности, возраст начала первой менструации (менархе)', 'type': 'text'},
        {'id': 'q_women_cycle_status', 'text': 'Какое у вас текущее состояние менструального цикла?', 'type': 'single'},
        {'id': 'q_women_pregnancy', 'text': 'Были ли у вас беременности или роды?', 'type': 'single'},
        {'id': 'q_women_cycle_length', 'text': 'Укажите продолжительность цикла от первого дня менструации до последнего дня цикла (в днях)', 'type': 'text'},
        {'id': 'q_women_menses_length', 'text': 'Укажите среднюю продолжительность менструации', 'type': 'single'},
        {'id': 'q_women_pms', 'text': 'Беспокоят ли вас симптомы ПМС? (можно выбрать несколько вариантов)', 'type': 'multi'},
        {'id': 'q_women_sleep_menses', 'text': 'Замечаете ли вы проблемы со сном накануне или во время менструации?', 'type': 'single'},
        {'id': 'q_women_flow_amount', 'text': 'Оцените обильность менструальных выделений по шкале от 1 до 10', 'type': 'text'},
        {'id': 'q_women_pain_level', 'text': 'Оцените болезненность во время менструации по шкале от 1 до 10', 'type': 'text'},
        {'id': 'q_women_flow_type', 'text': 'Как вы можете описать менструальные выделения?', 'type': 'single'},
        {'id': 'q_women_gut_menses', 'text': 'Бывает ли дискомфорт со стороны ЖКТ во время или накануне менструации?', 'type': 'single'},
        {'id': 'q_women_bleeding_other_days', 'text': 'Бывают ли кровянистые выделения в другие дни цикла?', 'type': 'single'},
        {'id': 'q_women_cystitis', 'text': 'Бывают ли у вас проявления цистита?', 'type': 'single'},
        {'id': 'q_women_candidiasis': ['Да', 'Нет'],
        'q_women_cosmetics_amount': ['3–4 и менее', '5–8', 'Около 10', 'Более 10'],
        'q_women_ecology': ['Да', 'Нет', 'Не в первую очередь'],
        'q_survey_end': []
    ]

    logic_rules_definitions_basic = [
        {'from': 'q_gender', 'answer': 'Мужчина', 'to': 'q_occupation'},
        {'from': 'q_gender', 'answer': 'Женщина', 'to': 'q_women_menarche'},
        {'from': 'q_occupation', 'answer': 'любой', 'to': 'q_sport_activity'},
        {'from': 'q_sport_activity', 'answer': 'любой', 'to': 'q_chronic_diseases'},
        {'from': 'q_chronic_diseases', 'answer': 'любой', 'to': 'q_family_diseases'},
        {'from': 'q_family_diseases', 'answer': 'любой', 'to': 'q_surgeries'},
        {'from': 'q_surgeries', 'answer': 'любой', 'to': 'q_medications'},
        {'from': 'q_medications', 'answer': 'любой', 'to': 'q_allergy'},
        {'from': 'q_allergy', 'answer': 'любой', 'to': 'q_orvi'},
        {'from': 'q_orvi', 'answer': 'любой', 'to': 'q_daily_routine'},
        {'from': 'q_daily_routine', 'answer': 'любой', 'to': 'q_sleep_quality'},
        {'from': 'q_sleep_quality', 'answer': 'любой', 'to': 'q_sleep_hygiene'},
        {'from': 'q_sleep_hygiene', 'answer': 'любой', 'to': 'q_muscle_symptoms'},
        {'from': 'q_muscle_symptoms', 'answer': 'любой', 'to': 'q_dizziness'},
        {'from': 'q_dizziness', 'answer': 'любой', 'to': 'q_pressure'},
        {'from': 'q_pressure', 'answer': 'любой', 'to': 'q_edema'},
        {'from': 'q_edema', 'answer': 'любой', 'to': 'q_urination'},
        {'from': 'q_urination', 'answer': 'любой', 'to': 'q_veins'},
        {'from': 'q_veins', 'answer': 'любой', 'to': 'q_water'},
        {'from': 'q_water', 'answer': 'любой', 'to': 'q_gut_pain'},
        {'from': 'q_gut_pain', 'answer': 'любой', 'to': 'q_gut_pain_relation'},
        {'from': 'q_gut_pain_relation', 'answer': 'любой', 'to': 'q_gut_heartburn'},
        {'from': 'q_gut_heartburn', 'answer': 'любой', 'to': 'q_gut_bloating'},
        {'from': 'q_gut_bloating', 'answer': 'любой', 'to': 'q_gut_appetite'},
        {'from': 'q_gut_appetite', 'answer': 'любой', 'to': 'q_gut_stool_regular'},
        {'from': 'q_gut_stool_regular', 'answer': 'любой', 'to': 'q_gut_stool_type'},
        {'from': 'q_gut_stool_type', 'answer': 'любой', 'to': 'q_gut_nausea'},
        {'from': 'q_gut_nausea', 'answer': 'любой', 'to': 'q_gut_hunger_break'},
        {'from': 'q_gut_hunger_break', 'answer': 'любой', 'to': 'q_gut_sleep_after_food'},
        {'from': 'q_gut_sleep_after_food', 'answer': 'любой', 'to': 'q_gut_food_intolerance'},
        {'from': 'q_gut_food_intolerance', 'answer': 'любой', 'to': 'q_skin_issues'},
        {'from': 'q_skin_issues', 'answer': 'любой', 'to': 'q_skin_doctor'},
        {'from': 'q_skin_doctor', 'answer': 'любой', 'to': 'q_nervous_problem_question'},
        {'from': 'q_nervous_problem_question', 'answer': 'Да', 'to': 'q_nervous_memory'},
        {'from': 'q_nervous_problem_question', 'answer': 'Нет', 'to': 'q_anemia_weakness'},
        {'from': 'q_nervous_memory', 'answer': 'любой', 'to': 'q_nervous_tics'},
        {'from': 'q_nervous_tics', 'answer': 'любой', 'to': 'q_nervous_communication'},
        {'from': 'q_nervous_communication', 'answer': 'любой', 'to': 'q_nervous_emotional'},
        {'from': 'q_nervous_emotional', 'answer': 'любой', 'to': 'q_nervous_stress_reaction'},
        {'from': 'q_nervous_stress_reaction', 'answer': 'любой', 'to': 'q_nervous_coping'},
        {'from': 'q_nervous_coping', 'answer': 'любой', 'to': 'q_nervous_decisions'},
        {'from': 'q_nervous_decisions', 'answer': 'любой', 'to': 'q_nervous_thinking'},
        {'from': 'q_nervous_thinking', 'answer': 'любой', 'to': 'q_anemia_weakness'},
        {'from': 'q_anemia_weakness', 'answer': 'любой', 'to': 'q_anemia_skin'},
        {'from': 'q_anemia_skin', 'answer': 'любой', 'to': 'q_anemia_taste'},
        {'from': 'q_anemia_taste', 'answer': 'любой', 'to': 'q_anemia_breath'},
        {'from': 'q_anemia_breath', 'answer': 'любой', 'to': 'q_anemia_smell'},
        {'from': 'q_anemia_smell', 'answer': 'любой', 'to': 'q_anemia_cheilitis'},
        {'from': 'q_anemia_cheilitis', 'answer': 'любой', 'to': 'q_anemia_meat'},
        {'from': 'q_anemia_meat', 'answer': 'любой', 'to': 'q_anemia_cold'},
        {'from': 'q_anemia_cold', 'answer': 'любой', 'to': 'q_oda_pain'},
        {'from': 'q_oda_pain', 'answer': 'любой', 'to': 'q_oda_pain_level'},
        {'from': 'q_oda_pain_level', 'answer': 'любой', 'to': 'q_oda_stiffness'},
        {'from': 'q_oda_stiffness', 'answer': 'любой', 'to': 'q_oda_diagnosis'},
        {'from': 'q_oda_diagnosis', 'answer': 'любой', 'to': 'q_oda_feet'},
        {'from': 'q_oda_feet', 'answer': 'любой', 'to': 'q_oda_shoes'},
        {'from': 'q_oda_shoes', 'answer': 'любой', 'to': 'q_oda_doctor'},
        {'from': 'q_oda_doctor', 'answer': 'любой', 'to': 'q_survey_end'},
        {'from': 'q_women_menarche', 'answer': 'любой', 'to': 'q_women_cycle_status'},
        {'from': 'q_women_cycle_status', 'answer': 'любой', 'to': 'q_women_pregnancy'},
        {'from': 'q_women_pregnancy', 'answer': 'любой', 'to': 'q_women_cycle_length'},
        {'from': 'q_women_cycle_length', 'answer': 'любой', 'to': 'q_women_menses_length'},
        {'from': 'q_women_menses_length', 'answer': 'любой', 'to': 'q_women_pms'},
        {'from': 'q_women_pms', 'answer': 'любой', 'to': 'q_women_sleep_menses'},
        {'from': 'q_women_sleep_menses', 'answer': 'любой', 'to': 'q_women_flow_amount'},
        {'from': 'q_women_flow_amount', 'answer': 'любой', 'to': 'q_women_pain_level'},
        {'from': 'q_women_pain_level', 'answer': 'любой', 'to': 'q_women_flow_type'},
        {'from': 'q_women_flow_type', 'answer': 'любой', 'to': 'q_women_gut_menses'},
        {'from': 'q_women_gut_menses', 'answer': 'любой', 'to': 'q_women_bleeding_other_days'},
        {'from': 'q_women_bleeding_other_days', 'answer': 'любой', 'to': 'q_women_cystitis'},
        {'from': 'q_women_cystitis', 'answer': 'любой', 'to': 'q_women_candidiasis'},
        {'from': 'q_women_candidiasis', 'answer': 'любой', 'to': 'q_women_cosmetics_amount'},
        {'from': 'q_women_cosmetics_amount', 'answer': 'любой', 'to': 'q_women_ecology'},
        {'from': 'q_women_ecology', 'answer': 'любой', 'to': 'q_nervous_problem_question'}, # Merge point for women's branch, then to nervous system
        {'from': 'q_survey_end', 'answer': 'любой', 'to': None}
    ]

    questions_to_add = []
    question_id_map = {} # Maps string ID (e.g., 'q_gender') to database ID

    for q_def in question_definitions_basic:
        options = options_data_basic.get(q_def['id'], [])
        q = Question(
            questionnaire_id=basic_questionnaire.id,
            text=q_def['text'],
            type=q_def['type'],
            options=options
        )
        questions_to_add.append(q)
    
    session.add_all(questions_to_add)
    await session.flush() # Flush to get IDs for all questions

    # Populate question_id_map after questions have IDs
    for i, q_def in enumerate(question_definitions_basic):
        question_id_map[q_def['id']] = questions_to_add[i].id

    logic_rules_to_add = []
    for rule_def in logic_rules_definitions_basic:
        from_q_id = question_id_map[rule_def['from']]
        to_q_id = question_id_map.get(rule_def['to']) if rule_def['to'] else None
        
        logic = QuestionLogic(
            question_id=from_q_id,
            answer_value=rule_def['answer'],
            next_question_id=to_q_id
        )
        logic_rules_to_add.append(logic)
    
    session.add_all(logic_rules_to_add)
    # No flush here

    logging.info("Seeding 'ayurved_m' questionnaire...")
    async with aiofiles.open('аюрвед_м.txt', 'r', encoding='utf-8') as f:
        ayurved_m_questions = json.loads(await f.read())
    ayurved_m_questionnaire = await _create_questionnaire_from_list(session, 'ayurved_m', ayurved_m_questions)

    logging.info("Seeding 'ayurved_j' questionnaire...")
    async with aiofiles.open('аюрвед_ж.txt', 'r', encoding='utf-8') as f:
        ayurved_j_questions = json.loads(await f.read())
    ayurved_j_questionnaire = await _create_questionnaire_from_list(session, 'ayurved_j', ayurved_j_questions)

    # Note: No session.flush() here, as _create_questionnaire_from_list handles its own flush.

    logging.info("Seeding tariffs...")
    tariffs_to_add = []
    tariffs_data = {
        'Базовый': {'price': 1000, 'description': 'Полная консультация'},
        'Сопровождение': {'price': 2000, 'description': 'Полная консультация с сопровождением'},
        'Повторная': {'price': 500, 'description': 'Повторная консультация'},
        'Лайт': {'price': 300, 'description': 'Экспресс-консультация'},
    }
    tariffs = {}
    for name, data in tariffs_data.items():
        tariff = Tariff(name=name, price=data['price'], description=data['description'])
        tariffs_to_add.append(tariff)
        tariffs[name] = tariff
    
    session.add_all(tariffs_to_add)
    await session.flush() # Flush to get IDs for tariffs before linking

    logging.info("Linking tariffs to questionnaires...")
    from .database.models import tariff_questionnaires_table # Import here to avoid circular dependency
    
    # Basic Tariff
    session.execute(tariff_questionnaires_table.insert().values(
        tariff_id=tariffs['Базовый'].id, questionnaire_id=basic_questionnaire.id
    ))
    session.execute(tariff_questionnaires_table.insert().values(
        tariff_id=tariffs['Базовый'].id, questionnaire_id=ayurved_m_questionnaire.id
    ))
    session.execute(tariff_questionnaires_table.insert().values(
        tariff_id=tariffs['Базовый'].id, questionnaire_id=ayurved_j_questionnaire.id
    ))

    # Support Tariff
    session.execute(tariff_questionnaires_table.insert().values(
        tariff_id=tariffs['Сопровождение'].id, questionnaire_id=basic_questionnaire.id
    ))
    session.execute(tariff_questionnaires_table.insert().values(
        tariff_id=tariffs['Сопровождение'].id, questionnaire_id=ayurved_m_questionnaire.id
    ))
    session.execute(tariff_questionnaires_table.insert().values(
        tariff_id=tariffs['Сопровождение'].id, questionnaire_id=ayurved_j_questionnaire.id
    ))

    # Lite Tariff
    session.execute(tariff_questionnaires_table.insert().values(
        tariff_id=tariffs['Лайт'].id, questionnaire_id=ayurved_m_questionnaire.id
    ))
    session.execute(tariff_questionnaires_table.insert().values(
        tariff_id=tariffs['Лайт'].id, questionnaire_id=ayurved_j_questionnaire.id
    ))
    
    await session.commit()
    logging.info("Database seeding completed successfully.")


async def on_startup(bot: Bot):
    startup_start_time = time.time()
    logging.info("--- Bot Starting Up ---")

    # Step 1: Initialize Database
    db_init_start = time.time()
    logging.info("Step 1: Initializing database tables...")
    from .database.session import async_engine
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logging.info(f"Step 1: Database tables initialized. (Took {time.time() - db_init_start:.4f}s)")

    async with async_session_maker() as session:
        seed_start = time.time()
        logging.info("Step 2: Checking if database needs to be seeded...")
        result = await session.execute(select(Tariff).limit(1))
        if not result.scalar_one_or_none():
            logging.info("No tariffs found. Seeding database...")
            await seed_database(session)
        else:
            logging.info(f"Step 2: Database already seeded. Skipping. (Took {time.time() - seed_start:.4f}s)")

        cache_load_start = time.time()
        logging.info("Step 3: Loading questionnaire cache from database...")
        await questionnaire_service.load_from_db(session)
        logging.info(f"Step 3: Questionnaire cache loaded. (Took {time.time() - cache_load_start:.4f}s)")

    webhook_setup_start = time.time()
    logging.info("Step 4: Configuring Telegram webhook...")
    if settings.WEBHOOK_HOST:
        webhook_url = f"{settings.WEBHOOK_HOST}{settings.WEBHOOK_PATH}"
        await bot.set_webhook(webhook_url)
        logging.info(f"Telegram Webhook set to {webhook_url}")
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Bot started in polling mode. Webhook deleted.")
    logging.info(f"Step 4: Webhook configured. (Took {time.time() - webhook_setup_start:.4f}s)")
    
    logging.info(f"--- Bot Startup Complete. Total time: {time.time() - startup_start_time:.4f}s ---")



async def on_shutdown(bot: Bot):
    if settings.WEBHOOK_HOST:
        logging.info("Shutting down and deleting Telegram webhook...")
        await bot.delete_webhook()
        logging.info("Telegram Webhook deleted.")


async def yookassa_webhook_handler(request: web.Request) -> web.Response:
    try:
        data = await request.text()
        notification_json = json.loads(data)
        notification = WebhookNotificationFactory().create(notification_json)
        
        bot: Bot = request.app['bot']
        dp: Dispatcher = request.app['dp']
        session_pool = request.app['session_pool']

        if notification.event == 'payment.succeeded':
            metadata = notification.object.metadata
            user_telegram_id = int(metadata.get('user_id'))
            
            async with session_pool() as session:
                user_result = await session.execute(
                    select(User).options(joinedload(User.tariff)).where(User.telegram_id == user_telegram_id)
                )
                user = user_result.scalar_one_or_none()
                
                if user and not user.has_paid:
                    user.has_paid = True
                    await session.commit()
                    
                    storage = dp.storage if dp.storage else MemoryStorage()
                    state = FSMContext(storage, key=str(user_telegram_id))

                    await payment_success.on_payment_success(bot, session, state, user)

                    admin_notification_text = (
                        f"💰 Оплата!\n"
                        f"User: @{user.username or 'N/A'} (ID: {user.telegram_id})\n"
                        f"Tariff: {user.tariff.name if user.tariff else 'N/A'}"
                    )
                    for admin_id in settings.admin_ids_list:
                        await bot.send_message(admin_id, admin_notification_text)
            
        return web.Response(status=200)

    except Exception as e:
        logging.error(f"Error processing YooKassa webhook: {e}", exc_info=True)
        return web.Response(status=500)


def main() -> None:
    init_engine()
    bot = Bot(token=settings.BOT_TOKEN.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.update.middleware(DbSessionMiddleware(session_pool=async_session_maker))
    dp.include_router(start.router)
    dp.include_router(tariff.router)
    dp.include_router(questionnaire.router)
    dp.include_router(booking.router)
    dp.include_router(admin.router)
    dp.include_router(payment_success.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    if settings.WEBHOOK_HOST:
        app = web.Application()
        app['bot'] = bot
        app['dp'] = dp
        app['session_pool'] = async_session_maker
        
        webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_requests_handler.register(app, path=settings.WEBHOOK_PATH)

        if settings.YOOKASSA_NOTIFICATION_URL:
            parsed_url = urlparse(settings.YOOKASSA_NOTIFICATION_URL)
            yookassa_webhook_path = parsed_url.path
            app.router.add_post(yookassa_webhook_path, yookassa_webhook_handler)
        
        setup_application(app, dp, bot=bot)
        web.run_app(app, host=settings.WEB_SERVER_HOST, port=settings.WEB_SERVER_PORT)
    else:
        asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)
        time.sleep(5)
        sys.exit(1)
