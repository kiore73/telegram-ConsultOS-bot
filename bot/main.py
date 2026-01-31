# VERSION 17: Simplified and Corrected Seeding
print("---> RUNNING MAIN.PY VERSION 17 ---")
import asyncio
import logging
import sys
from urllib.parse import urlparse
import json

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from sqlalchemy import select
from yookassa.domain.notification import WebhookNotificationFactory, WebhookNotification

from .config import settings
from .database.models import Base, Questionnaire, Question, QuestionLogic, User, Payment
from .database.session import async_engine, async_session_maker
from .handlers import start, payment, questionnaire, booking, admin
from .middlewares.db import DbSessionMiddleware
from .services.questionnaire_service import questionnaire_service

logging.basicConfig(level=logging.INFO, stream=sys.stdout)


async def seed_questionnaire(session):
    """
    Populates the database with the new, structured questionnaire.
    This version is declarative and robust.
    """
    logging.info("Seeding new questionnaire data...")
    main_questionnaire = Questionnaire(title="Основной опросник")
    session.add(main_questionnaire)
    await session.flush()

    # 1. Define all questions
    question_defs = {
        'q_gender': {'text': 'Укажите ваш пол', 'type': 'single', 'options': ['Мужчина', 'Женщина']},
        'q_occupation': {'text': 'Ваш род занятий, работа (можно выбрать несколько вариантов)', 'type': 'multi', 'options': ['Сидячая', 'Присутствует физическая нагрузка', 'Высокая умственная нагрузка / высокий уровень ответственности', 'Приходится долго стоять', 'Много разъездов, поездок, перелетов']},
        'q_sport_activity': {'text': 'Присутствуют ли в вашей жизни спорт или физическая активность?', 'type': 'single', 'options': ['Да, регулярно', 'Нерегулярно, время от времени', 'Нет и не было', 'Я профессиональный спортсмен']},
        'q_chronic_diseases': {'text': 'Если у вас есть или были хронические или наследственные заболевания, укажите диагнозы', 'type': 'text'},
        'q_family_diseases': {'text': 'Есть ли хронические или генетические заболевания у ваших ближайших биологических родственников?', 'type': 'text'},
        'q_surgeries': {'text': 'Были ли у вас операции? Если да, какие и как давно?', 'type': 'text'},
        'q_medications': {'text': 'Принимаете ли вы на постоянной основе фармацевтические препараты или БАДы? Если да, укажите какие', 'type': 'text'},
        'q_allergy': {'text': 'Испытываете ли вы симптомы аллергии?', 'type': 'single', 'options': ['Очень часто', 'Иногда', 'Сезонно', 'Нет']},
        'q_orvi': {'text': 'Как часто вы переносите сезонные ОРВИ?', 'type': 'single', 'options': ['Очень редко', '1–2 раза в год', '3–4 раза в год', 'Постоянно, даже летом']},
        'q_daily_routine': {'text': 'Опишите кратко ваш режим дня (сон, питание, работа, транспорт, хобби, прогулки)', 'type': 'text'},
        'q_sleep_quality': {'text': 'Оцените качество вашего сна (можно выбрать несколько вариантов)', 'type': 'multi', 'options': ['Быстро засыпаю', 'Требуется более 40 минут для засыпания', 'Сон без пробуждений', 'Сон чуткий, есть пробуждения', 'Есть трекер сна', 'Просыпаюсь легко и чувствую восстановление', 'Просыпаюсь тяжело, но потом бодр', 'Тяжело проснуться, нет сил до обеда']},
        'q_sleep_hygiene': {'text': 'Знакомы ли вы с правилами и гигиеной здорового сна?', 'type': 'single', 'options': ['Да, стараюсь придерживаться', 'Да, но не получается соблюдать', 'Нет, не знаком']},
        'q_muscle_symptoms': {'text': 'Наблюдали ли вы у себя мышечные судороги, слабость или онемение?', 'type': 'multi', 'options': ['Нет', 'Судороги ног ночью', 'Спазмы мышц шеи', 'Судороги или спазмы регулярно', 'Онемение конечностей']},
        'q_dizziness': {'text': 'Испытываете ли вы головокружение?', 'type': 'single', 'options': ['Да, часто', 'Иногда', 'Нет']},
        'q_pressure': {'text': 'Знаете ли вы свое артериальное давление и пульс?', 'type': 'single', 'options': ['Не знаю', 'Повышенное / гипертония', 'Пониженное', 'Нестабильное', 'Есть трекер']},
        'q_edema': {'text': 'Беспокоят ли вас отеки?', 'type': 'multi', 'options': ['Нет', 'Постоянно', 'Летом', 'В области ног', 'Лицо и руки']},
        'q_urination': {'text': 'Бывают ли стрессовые или ночные позывы к мочеиспусканию?', 'type': 'single', 'options': ['Да', 'Иногда', 'Нет']},
        'q_veins': {'text': 'Беспокоят ли вас вены, сосудистые звездочки, варикоз, тяжесть в ногах?', 'type': 'single', 'options': ['Нет', 'Иногда', 'Часто']},
        'q_water': {'text': 'Оцените ваш питьевой режим', 'type': 'multi', 'options': ['Пью достаточно воды', 'Воду не люблю, пью другие напитки', 'Забываю пить, часто жажда', 'Не чувствую жажды', 'Пью много, жажда не утоляется']},
        'q_gut_pain': {'text': 'Испытываете ли вы болевые ощущения или дискомфорт в животе?', 'type': 'multi', 'options': ['В верхней части живота (эпигастрий)', 'В области пупка', 'Внизу живота', 'Больше справа', 'Больше слева или в области спины', 'Нет']},
        'q_gut_pain_relation': {'text': 'Если есть боли, связаны ли они с приемом пищи?', 'type': 'single', 'options': ['Сразу после еды', 'В течение 1–2 часов', 'Связаны с голодом', 'Не связаны', 'Бывает по-разному']},
        'q_gut_heartburn': {'text': 'Беспокоят ли вас изжога, жжение за грудиной, отрыжка, нарушение глотания?', 'type': 'single', 'options': ['Часто', 'Иногда', 'Нет']},
        'q_gut_bloating': {'text': 'Беспокоят ли вас вздутие живота или метеоризм?', 'type': 'single', 'options': ['Нет', 'Иногда', 'Постоянно']},
        'q_gut_appetite': {'text': 'Оцените ваш аппетит', 'type': 'single', 'options': ['Стабильно хороший', 'Все время хочется есть', 'Плохой', 'Нестабильный']},
        'q_gut_stool_regular': {'text': 'Какая регулярность стула?', 'type': 'single', 'options': ['Ежедневный по утрам', 'Ежедневный в разное время', 'Несколько раз в сутки', 'Непредсказуемый', 'Не каждый день']},
        'q_gut_stool_type': {'text': 'Оцените характер стула', 'type': 'single', 'options': ['Нормальный, оформленный', 'Склонность к диарее', 'Очень плотный', 'Нестабильный', 'Есть примеси']},
        'q_gut_nausea': {'text': 'Испытываете ли вы тошноту?', 'type': 'multi', 'options': ['Бывает иногда', 'На определенные продукты', 'Очень редко', 'При укачивании']},
        'q_gut_hunger_break': {'text': 'Как вы переносите длительные перерывы между приемами пищи?', 'type': 'single', 'options': ['Нормально', 'Появляется слабость, головокружение', 'Очень плохо']},
        'q_gut_sleep_after_food': {'text': 'Испытываете ли вы сонливость после еды?', 'type': 'single', 'options': ['Да', 'Нет', 'Бывает редко']},
        'q_gut_food_intolerance': {'text': 'Есть ли продукты, после которых вы замечаете ухудшение самочувствия?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_skin_issues': {'text': 'Что вас не устраивает в состоянии кожи? (можно выбрать несколько вариантов)', 'type': 'multi', 'options': ['Сухость, раздражение', 'Изменение цвета', 'Высыпания, дерматиты', 'Акне', 'Повышенная жирность', 'Папилломы, родинки', 'Бородавки', 'Потеря упругости', 'Стрии', 'Зуд', 'Возрастные изменения', 'Отечность', 'Витилиго', 'Псориаз', 'Новообразования', 'Грибок']},
        'q_skin_doctor': {'text': 'Обращались ли вы к специалисту по поводу кожи?', 'type': 'single', 'options': ['Да', 'Нет', 'Постоянно наблюдаюсь']},
        'q_nervous_problem_question': {'text': 'Есть ли у вас проблемы с нервной системой или повышенный уровень стресса?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_nervous_memory': {'text': 'Как вы оцениваете свою память?', 'type': 'multi', 'options': ['Все хорошо', 'Страдает кратковременная память', 'Плохо удерживаю информацию', 'Все забываю', 'Забываю слова и имена']},
        'q_nervous_tics': {'text': 'Наблюдаете ли вы тики или непроизвольные движения?', 'type': 'single', 'options': ['Да', 'Иногда', 'Нет']},
        'q_nervous_communication': {'text': 'Как вы ощущаете себя в общении с людьми?', 'type': 'single', 'options': ['Легко общаюсь', 'Устаю от общения', 'Предпочитаю одиночество', 'Не могу без общения']},
        'q_nervous_emotional': {'text': 'Устраивает ли вас ваше эмоциональное состояние?', 'type': 'single', 'options': ['Да', 'Нет', 'Наблюдаюсь у специалиста']},
        'q_nervous_stress_reaction': {'text': 'Как вы реагируете на стресс?', 'type': 'single', 'options': ['Адекватно', 'Остро', 'С поддержкой препаратов']},
        'q_nervous_coping': {'text': 'Есть ли у вас навыки управления стрессом?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_nervous_decisions': {'text': 'Насколько легко вам принимать решения?', 'type': 'single', 'options': ['Легко', 'Сложно', 'Зависит от ситуации']},
        'q_nervous_thinking': {'text': 'Устраивает ли вас уровень мышления и умственной работоспособности?', 'type': 'single', 'options': ['Да', 'Кажется, снижается', 'Не устраивает']},
        'q_anemia_weakness': {'text': 'Беспокоит ли вас слабость или быстрая утомляемость?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_anemia_skin': {'text': 'Замечаете ли вы бледность кожи или выпадение волос?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_anemia_taste': {'text': 'Бывают ли необычные вкусовые желания (мел, лед и т.п.)?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_anemia_breath': {'text': 'Бывает ли одышка или учащенное сердцебиение при легкой нагрузке?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_anemia_smell': {'text': 'Есть ли тяга к необычным запахам (лак, бензин и т.п.)?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_anemia_cheilitis': {'text': 'Беспокоят ли заеды в углах рта?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_anemia_meat': {'text': 'Есть ли отвращение к мясу или продуктам?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_anemia_cold': {'text': 'Отмечаете ли повышенную зябкость рук и ног?', 'type': 'single', 'options': ['Нет', 'Иногда', 'Часто']},
        'q_oda_pain': {'text': 'Беспокоят ли вас болевые ощущения?', 'type': 'multi', 'options': ['В суставах', 'В позвоночнике', 'В мышцах', 'Не беспокоят']},
        'q_oda_pain_level': {'text': 'Оцените интенсивность боли по шкале от 1 до 10', 'type': 'text'},
        'q_oda_stiffness': {'text': 'Есть ли скованность или тугоподвижность суставов?', 'type': 'single', 'options': ['Да', 'Нет', 'Только по утрам', 'В определенном положении']},
        'q_oda_diagnosis': {'text': 'Есть ли диагностированные заболевания ОДА (грыжи, артрит и т.п.)?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_oda_feet': {'text': 'Есть ли патологии стопы?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_oda_shoes': {'text': 'Изменился ли размер обуви?', 'type': 'single', 'options': ['Нет', 'Покупаю на 1–2 размера больше', 'Сложно подобрать удобную']},
        'q_oda_doctor': {'text': 'Обращались ли вы к специалисту?', 'type': 'multi', 'options': ['Нет', 'Невролог', 'Травматолог-ортопед', 'Хирург', 'Мануальный терапевт', 'Остеопат']},
        'q_women_menarche': {'text': 'Укажите, по возможности, возраст начала первой менструации (менархе)', 'type': 'text'},
        'q_women_cycle_status': {'text': 'Какое у вас текущее состояние менструального цикла?', 'type': 'single', 'options': ['Регулярный цикл', 'Нерегулярный цикл', 'Менопауза', 'Беременность или грудное вскармливание']},
        'q_women_pregnancy': {'text': 'Были ли у вас беременности или роды?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_women_cycle_length': {'text': 'Укажите продолжительность цикла от первого дня менструации до последнего дня цикла (в днях)', 'type': 'text'},
        'q_women_menses_length': {'text': 'Укажите среднюю продолжительность менструации', 'type': 'single', 'options': ['Не более 3 дней', '3–4 дня', '5–6 дней', 'Более 6 дней']},
        'q_women_pms': {'text': 'Беспокоят ли вас симптомы ПМС? (можно выбрать несколько вариантов)', 'type': 'multi', 'options': ['Болезненность или набухание молочных желез', 'Эмоциональная лабильность, раздражительность', 'Расстройства пищевого поведения', 'Боли внизу живота или пояснице', 'Не беспокоят']},
        'q_women_sleep_menses': {'text': 'Замечаете ли вы проблемы со сном накануне или во время менструации?', 'type': 'single', 'options': ['Да', 'Нет', 'Бывает']},
        'q_women_flow_amount': {'text': 'Оцените обильность менструальных выделений по шкале от 1 до 10', 'type': 'text'},
        'q_women_pain_level': {'text': 'Оцените болезненность во время менструации по шкале от 1 до 10', 'type': 'text'},
        'q_women_flow_type': {'text': 'Как вы можете описать менструальные выделения?', 'type': 'single', 'options': ['Кровь красного цвета без сгустков', 'Темные выделения со сгустками или слизью', 'Темные выделения без сгустков', 'Мажущие выделения']},
        'q_women_gut_menses': {'text': 'Бывает ли дискомфорт со стороны ЖКТ во время или накануне менструации?', 'type': 'single', 'options': ['Да', 'Нет', 'Иногда']},
        'q_women_bleeding_other_days': {'text': 'Бывают ли кровянистые выделения в другие дни цикла?', 'type': 'single', 'options': ['Мажущие', 'Обильные', 'Нет']},
        'q_women_cystitis': {'text': 'Бывают ли у вас проявления цистита?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_women_candidiasis': {'text': 'Беспокоят ли вас симптомы молочницы или вагинального дисбиоза?', 'type': 'single', 'options': ['Да', 'Нет']},
        'q_women_cosmetics_amount': {'text': 'Сколько косметических средств вы используете ежедневно?', 'type': 'single', 'options': ['3–4 и менее', '5–8', 'Около 10', 'Более 10']},
        'q_women_ecology': {'text': 'Уделяете ли вы внимание экологичности и безопасности косметических средств?', 'type': 'single', 'options': ['Да', 'Нет', 'Не в первую очередь']},
        'q_survey_end': {'text': 'Спасибо за ваши ответы! Опросник завершен.', 'type': 'final'},
    }

    # 2. Create Question objects and map string IDs to DB IDs
    question_map = {}
    for str_id, q_data in question_defs.items():
        q = Question(questionnaire_id=main_questionnaire.id, text=q_data['text'], type=q_data['type'])
        session.add(q)
        question_map[str_id] = q
    await session.flush()

    # 3. Define all logic branches declaratively
    logic_rules = [
        # Start -> Common Block
        {'from': 'q_gender', 'answer': 'Мужчина', 'to': 'q_occupation'},
        {'from': 'q_gender', 'answer': 'Женщина', 'to': 'q_occupation'},
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
        
        # This is the point where logic diverges. The handler will now manage this.
        {'from': 'q_oda_doctor', 'answer': 'любой', 'to': 'q_women_menarche'}, 
        {'from': 'q_oda_pain', 'answer': 'Не беспокоят', 'to': 'q_women_menarche'},

        # Women's Branch
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
        {'from': 'q_women_ecology', 'answer': 'любой', 'to': 'q_survey_end'},
    ]

    # 4. Create QuestionLogic entries
    for rule in logic_rules:
        # Skip rules that don't exist in the question map (like internal nodes)
        if rule['from'] not in question_map:
            continue
        
        from_id = question_map[rule['from']].id
        to_id = question_map.get(rule['to']).id if rule.get('to') else None
        
        # For questions with pre-defined options, create a rule for each option
        if rule['answer'] == 'любой' and question_defs[rule['from']].get('options'):
             for option in question_defs[rule['from']]['options']:
                # Do not create a rule for 'Не беспокоят' if a specific one exists
                if rule['from'] == 'q_oda_pain' and option == 'Не беспокоят':
                    continue
                
                session.add(QuestionLogic(
                     question_id=from_id,
                     answer_value=option,
                     next_question_id=to_id
                 ))
        # For all other cases (specific answers, or 'любой' for text inputs)
        else:
            session.add(QuestionLogic(
                question_id=from_id,
                answer_value=rule['answer'],
                next_question_id=to_id
            ))

    await session.commit()
    logging.info("Questionnaire data seeded successfully with new logic.")


async def on_startup(bot: Bot):
    """
    Handles bot startup. Initializes DB, loads questionnaire cache, and sets webhook.
    """
    logging.info("Initializing database tables...")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logging.info("Database tables initialized.")
    
    async with async_session_maker() as session:
        if not (await session.execute(select(Question))).first():
            await seed_questionnaire(session)

    async with async_session_maker() as session:
        await questionnaire_service.load_from_db(session)

    if settings.WEBHOOK_HOST:
        webhook_url = f"{settings.WEBHOOK_HOST}{settings.WEBHOOK_PATH}"
        await bot.set_webhook(webhook_url)
        logging.info(f"Telegram Webhook set to {webhook_url}")
        if settings.YOOKASSA_NOTIFICATION_URL:
            logging.info(f"YooKassa Notifications expected at: {settings.YOOKASSA_NOTIFICATION_URL}")
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Bot started in polling mode. Webhook deleted.")


async def on_shutdown(bot: Bot):
    """Handles bot shutdown."""
    if settings.WEBHOOK_HOST:
        logging.info("Shutting down and deleting Telegram webhook...")
        await bot.delete_webhook()
        logging.info("Telegram Webhook deleted.")


async def yookassa_webhook_handler(request: web.Request) -> web.Response:
    """
    Handles incoming notifications from YooKassa.
    """
    try:
        data = await request.text()
        logging.info(f"Received YooKassa webhook: {data}")
        notification_json = json.loads(data)
        notification = WebhookNotificationFactory().create(notification_json)
        
        bot: Bot = request.app['bot']
        session_pool = request.app['session_pool']

        logging.info(f"YooKassa event: {notification.event}")

        if notification.event == 'payment.succeeded':
            logging.info("Processing 'payment.succeeded' event...")
            payment_id_yk = notification.object.id
            user_telegram_id = notification.object.metadata.get('user_id')
            logging.info(f"YooKassa Payment ID: {payment_id_yk}, User Telegram ID from metadata: {user_telegram_id}")

            async with session_pool() as session:
                user = (await session.execute(select(User).where(User.telegram_id == int(user_telegram_id)))).scalar_one_or_none()
                payment_record = (await session.execute(select(Payment).where(Payment.provider_charge_id == payment_id_yk))).scalar_one_or_none()

                logging.info(f"DB user found: {'Yes' if user else 'No'}")
                logging.info(f"DB payment record found: {'Yes' if payment_record else 'No'}")

                if user and payment_record:
                    logging.info(f"User '{user_telegram_id}' has_paid status BEFORE update: {user.has_paid}")
                    if not user.has_paid:
                        user.has_paid = True
                        payment_record.status = "succeeded"
                        await session.commit()
                        logging.info(f"User '{user_telegram_id}' and payment '{payment_id_yk}' status updated to paid/succeeded in DB.")

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
                        logging.info(f"Confirmation message sent to user {user.telegram_id}.")
                        
                        admin_notification_text = (
                            f"💰 <b>Оплата подтверждена!</b>\n\n"
                            f"Пользователь: @{user.username or 'N/A'} (ID: <code>{user.telegram_id}</code>)\n"
                            f"Сумма: {notification.object.amount.value} {notification.object.amount.currency}\n"
                            f"YooKassa ID: <code>{payment_id_yk}</code>"
                        )
                        for admin_id in settings.admin_ids_list:
                            try:
                                await bot.send_message(admin_id, admin_notification_text)
                                logging.info(f"Admin notification sent to {admin_id}.")
                            except Exception as e:
                                logging.error(f"Failed to send notification to admin {admin_id}: {e}")
                    else:
                        logging.info(f"User {user_telegram_id} already marked as paid. Skipping confirmation message.")
                else:
                    logging.error(f"Webhook processing failed: User or Payment record not found for YK Payment ID {payment_id_yk}.")
            
        elif notification.event == 'payment.canceled':
            logging.warning(f"YooKassa payment {notification.object.id} was canceled.")

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

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    if settings.WEBHOOK_HOST:
        logging.info("Starting bot in webhook mode...")
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
        asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")