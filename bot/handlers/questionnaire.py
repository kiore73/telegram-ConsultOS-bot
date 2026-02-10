from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from ..states.questionnaire import QuestionnaireFSM
from ..states.booking import BookingFSM
from ..keyboards.questionnaire import get_question_keyboard
from ..keyboards.booking import get_calendar_keyboard

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from ..database.models import User, Tariff # Add User and Tariff imports

router = Router()

def _get_questionnaire_service():
    from ..services import questionnaire_service
    return questionnaire_service

async def end_current_questionnaire_and_proceed(bot: Bot, chat_id: int, message_id: int, state: FSMContext, session: AsyncSession):
    """
    Checks for pending questionnaires and starts the next one, or moves to booking.
    """
    data = await state.get_data()
    pending = data.get("pending_questionnaires", [])
    current_q_title = data.get("current_questionnaire_title")

    user_result = await session.execute(
        select(User).options(joinedload(User.tariff)).where(User.telegram_id == chat_id)
    )
    user = user_result.scalar_one_or_none()

    if user and user.tariff and user.tariff.name in ["Базовый", "Сопровождение"] and current_q_title == "basic":
        answers = data.get("answers", {})
        basic_q_cache = _get_questionnaire_service().get_questionnaire_by_title("basic")
        
        gender_question_id = None
        for q_id, q_obj in basic_q_cache.questions.items():
            if q_obj.text == "Укажите ваш пол":
                gender_question_id = q_obj.id
                break
        
        if gender_question_id:
            gender_answer = answers.get(str(gender_question_id))
            if gender_answer == "Мужчина":
                pending.append("ayurved_m")
            elif gender_answer == "Женщина":
                pending.append("ayurved_j")
            await state.update_data(pending_questionnaires=pending) # Update state with new pending
        
    if pending:
        await _get_questionnaire_service().start_questionnaire(bot, chat_id, message_id, state, session)
    else:
        await state.set_state(BookingFSM.DATE_SELECT)
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text="Спасибо за ответы! Теперь выберите удобную дату для консультации:",
            reply_markup=await get_calendar_keyboard(session)
        )

async def show_question(bot: Bot, chat_id: int, message_id: int, state: FSMContext, session: AsyncSession, question_id: int):
    """ Helper function to display a question. """
    data = await state.get_data()
    current_q_title = data.get("current_questionnaire_title")
    
    q_cache = _get_questionnaire_service().get_questionnaire_by_title(current_q_title)
    question = q_cache.get_question(question_id)

    if not question or question.type == 'final':
        await end_current_questionnaire_and_proceed(bot, chat_id, message_id, state, session)
        return
    
    selected_answers = data.get(f"multi_answers_{question_id}", [])
    keyboard = get_question_keyboard(question, selected_answers)
    
    await bot.edit_message_text(
        chat_id=chat_id, message_id=message_id,
        text=f"Вопрос:\n\n{question.text}",
        reply_markup=keyboard
    )
    await state.update_data(current_question_id=question.id)

async def process_answer(state: FSMContext, question_id: int, answer_value):
    """ Saves the answer and determines the next question. """
    data = await state.get_data()
    current_q_title = data.get("current_questionnaire_title")
    q_cache = _get_questionnaire_service().get_questionnaire_by_title(current_q_title)
    question = q_cache.get_question(question_id)
    
    if current_q_title == 'basic' and "Укажите ваш пол" in question.text:
        pending = data.get("pending_questionnaires", [])
        if answer_value == "Мужчина":
            pending.append("ayurved_m")
        elif answer_value == "Женщина":
            pending.append("ayurved_j")
        await state.update_data(pending_questionnaires=pending)

    answers = data.get("answers", {})
    logic_answer = answer_value
    if question.type == 'multi':
        answers[str(question_id)] = json.dumps(answer_value, ensure_ascii=False)
        logic_answer = "любой"
    else:
        answers[str(question_id)] = answer_value
    
    history = data.get("question_history", [])
    if question_id not in history:
        history.append(question_id)
    
    await state.update_data(answers=answers, question_history=history)
    
    return q_cache.get_next_question_id(question_id, logic_answer)

@router.callback_query(QuestionnaireFSM.IN_QUESTIONNAIRE, F.data.startswith("q_"))
async def answer_handler(cb: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    parts = cb.data.split('_')
    question_id = int(parts[1])
    option_index = int(parts[2])
    
    data = await state.get_data()
    current_q_title = data.get("current_questionnaire_title")
    q_cache = _get_questionnaire_service().get_questionnaire_by_title(current_q_title)
    question = q_cache.get_question(question_id)
    answer_text = question.options[option_index]
    
    next_question_id = await process_answer(state, question_id, answer_text)

    if next_question_id:
        await show_question(cb.bot, cb.from_user.id, cb.message.message_id, state, session, next_question_id)
    else:
        await end_current_questionnaire_and_proceed(cb.bot, cb.from_user.id, cb.message.message_id, state, session)
    
    await cb.answer()
