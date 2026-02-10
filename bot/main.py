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
# ... (rest of the imports and functions before seed_database)

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
        'q_sleep_hygiene': ['Да', 'стараюсь придерживаться', 'Да', 'но не получается соблюдать', 'Нет', 'не знаком'],
        'q_muscle_symptoms': ['Нет', 'Судороги ног ночью', 'Спазмы мышц шеи', 'Судороги или спазмы регулярно', 'Онемение конечностей'],
        'q_dizziness': ['Да', 'часто', 'Иногда', 'Нет'],
        'q_pressure': ['Не знаю', 'Повышенное / гипертония', 'Пониженное', 'Нестабильное', 'Есть трекер'],
        'q_edema': ['Нет', 'Постоянно', 'Летом', 'отекают ноги/лодыжки', 'Лицо и руки'],
        'q_urination': ['Да', 'Иногда', 'Нет'],
        'q_veins': ['Нет', 'беспокоит тяжесть', 'Часто'],
        'q_water': ['Пью достаточно воды', 'Воду не люблю', 'пью другие напитки', 'Забываю пить', 'часто жажда', 'Не чувствую жажды', 'Пью много', 'жажда не утоляется'],
        'q_gut_pain': ['В верхней части живота (эпигастрий)', 'В области пупка', 'Внизу живота', 'Больше справа', 'Больше слева или в области спины', 'Нет'],
        'q_gut_pain_relation': ['Сразу после еды', 'В течение 1–2 часов', 'Связаны с голодом', 'Не связаны', 'Бывает по-разному'],
        'q_gut_heartburn': ['Часто', 'Иногда', 'Нет'],
        'q_gut_bloating': ['Нет', 'Иногда', 'Постоянно'],
        'q_gut_appetite': ['Стабильно хороший', 'Все время хочется есть', 'Плохой', 'Нестабильный'],
        'q_gut_stool_regular': ['Ежедневный по утрам', 'Ежедневный в разное время', 'Несколько раз в сутки', 'Непредсказуемый', 'Не каждый день'],
        'q_gut_stool_type': ['Нормальный', 'оформленный', 'Склонность к диарее', 'Очень плотный', 'Нестабильный', 'Есть примеси'],
        'q_gut_nausea': ['Бывает иногда', 'На определенные продукты', 'Очень редко', 'При укачивании'],
        'q_gut_hunger_break': ['Нормально', 'Появляется слабость', 'головокружение', 'Очень плохо'],
        'q_gut_sleep_after_food': ['Да', 'Нет', 'Бывает редко'],
        'q_gut_food_intolerance': ['Да', 'Нет'],
        'q_skin_issues': ['Сухость', 'раздражение', 'Изменение цвета', 'Высыпания', 'дерматиты', 'Акне', 'Повышенная жирность', 'Папилломы', 'родинки', 'Бородавки', 'Потеря упругости', 'Стрии', 'Зуд', 'Возрастные изменения', 'Отечность', 'Витилиго', 'Псориаз', 'Новообразования', 'Грибок'],
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
        {'id': 'q_nervous_emotional': ['Да', 'Нет', 'Наблюдаюсь у специалиста'],
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
    }