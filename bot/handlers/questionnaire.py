import json
import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..states.questionnaire import QuestionnaireFSM
from ..states.booking import BookingFSM
from ..database.models import Question, QuestionLogic, Answer, User
from ..keyboards.questionnaire import get_question_keyboard
from ..keyboards.booking import get_calendar_keyboard

router = Router()


async def show_question(bot: Bot, chat_id: int, message_id: int, state: FSMContext, session: AsyncSession, question_id: int):
    """ Helper function to display a question. """
    result = await session.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()

    if not question:
        await bot.send_message(chat_id, "Опросник завершен или произошла ошибка.")
        await state.clear()
        return

    if "Спасибо" in question.text:
        await state.set_state(BookingFSM.DATE_SELECT)
        calendar_keyboard = await get_calendar_keyboard(session)
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text="Спасибо за ответы! Теперь выберите удобную дату для консультации:",
            reply_markup=calendar_keyboard
        )
        return
    
    current_data = await state.get_data()
    selected_answers = current_data.get(f"multi_answers_{question_id}", [])
    
    keyboard = await get_question_keyboard(question, session, selected_answers)
    await bot.edit_message_text(
        chat_id=chat_id, message_id=message_id,
        text=f"Вопрос:\n\n{question.text}",
        reply_markup=keyboard
    )
    await state.update_data(current_question_id=question.id)


async def process_answer(state: FSMContext, session: AsyncSession, question_id: int, answer_value):
    """ Saves the answer and determines the next question. """
    current_data = await state.get_data()
    answers = current_data.get("answers", {})
    
    if isinstance(answer_value, list):
        answers[str(question_id)] = json.dumps(answer_value, ensure_ascii=False)
        # For branching logic, we'll use a generic "любой" for multi-choice
        logic_answer_value = "любой"
    else:
        answers[str(question_id)] = answer_value
        logic_answer_value = answer_value

    question_history = current_data.get("question_history", [])
    if question_id not in question_history:
        question_history.append(question_id)
    
    await state.update_data(answers=answers, question_history=question_history)

    result = await session.execute(
        select(QuestionLogic).where(QuestionLogic.question_id == question_id, QuestionLogic.answer_value == logic_answer_value)
    )
    logic = result.scalar_one_or_none()
    
    if not logic:
        result = await session.execute(
            select(QuestionLogic).where(QuestionLogic.question_id == question_id, QuestionLogic.answer_value == "любой")
        )
        logic = result.scalar_one_or_none()

    return logic.next_question_id if logic else None


async def go_to_next_question(bot: Bot, chat_id: int, message_id: int, state: FSMContext, session: AsyncSession, next_question_id: int):
    """ Transitions to the next question or ends the questionnaire. """
    if next_question_id:
        await show_question(bot, chat_id, message_id, state, session, next_question_id)
    else:
        await state.set_state(BookingFSM.DATE_SELECT)
        calendar_keyboard = await get_calendar_keyboard(session)
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text="Спасибо за ответы! Теперь выберите удобную дату для консультации:",
            reply_markup=calendar_keyboard
        )


@router.callback_query(F.data == "start_questionnaire")
async def start_questionnaire_handler(cb: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.set_state(QuestionnaireFSM.IN_QUESTIONNAIRE)
    await state.update_data(question_history=[], answers={})
    await show_question(cb.bot, cb.from_user.id, cb.message.message_id, state, session, question_id=1)
    await cb.answer()


@router.callback_query(F.data.startswith("answer:"))
async def answer_handler(cb: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    _, q_id_str, answer_value = cb.data.split(":", 2)
    next_question_id = await process_answer(state, session, int(q_id_str), answer_value)
    await go_to_next_question(cb.bot, cb.from_user.id, cb.message.message_id, state, session, next_question_id)
    await cb.answer()


@router.callback_query(F.data.startswith("multi_answer:"))
async def multi_answer_handler(cb: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    _, q_id_str, answer_value = cb.data.split(":", 2)
    question_id = int(q_id_str)
    
    current_data = await state.get_data()
    selected_key = f"multi_answers_{question_id}"
    selected_for_q = current_data.get(selected_key, [])
    
    if answer_value in selected_for_q:
        selected_for_q.remove(answer_value)
    else:
        selected_for_q.append(answer_value)
        
    await state.update_data({selected_key: selected_for_q})
    await show_question(cb.bot, cb.from_user.id, cb.message.message_id, state, session, question_id)
    await cb.answer()


@router.callback_query(F.data.startswith("multi_done:"))
async def multi_done_handler(cb: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    _, q_id_str = cb.data.split(":", 1)
    question_id = int(q_id_str)
    
    current_data = await state.get_data()
    selected_answers = current_data.get(f"multi_answers_{question_id}", [])
    
    next_question_id = await process_answer(state, session, question_id, selected_answers)
    await go_to_next_question(cb.bot, cb.from_user.id, cb.message.message_id, state, session, next_question_id)
    await cb.answer()


@router.message(QuestionnaireFSM.IN_QUESTIONNAIRE, F.photo)
async def photo_answer_handler(message: types.Message, state: FSMContext, session: AsyncSession):
    current_data = await state.get_data()
    question_id = current_data.get("current_question_id")
    question = (await session.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()

    if question and question.type == 'photo':
        photo_file_id = message.photo[-1].file_id
        next_question_id = await process_answer(state, session, question_id, photo_file_id)
        # Need to edit the original message, not reply. This is tricky.
        # For now, let's send a new message.
        await message.answer("Фото получено. Следующий вопрос:")
        sent_message = await message.answer(".")
        await go_to_next_question(message.bot, message.from_user.id, sent_message.message_id, state, session, next_question_id)
    else:
        await message.answer("Пожалуйста, ответьте на текущий вопрос или отправьте фото, если это требуется.")


@router.callback_query(F.data.startswith("skip_question:"))
async def skip_question_handler(cb: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    _, q_id_str = cb.data.split(":", 1)
    next_question_id = await process_answer(state, session, int(q_id_str), "skipped")
    await go_to_next_question(cb.bot, cb.from_user.id, cb.message.message_id, state, session, next_question_id)
    await cb.answer()


@router.message(QuestionnaireFSM.IN_QUESTIONNAIRE, F.text)
async def text_answer_handler(message: types.Message, state: FSMContext, session: AsyncSession):
    current_data = await state.get_data()
    question_id = current_data.get("current_question_id")
    question = (await session.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()

    if question and question.type == 'text':
        next_question_id = await process_answer(state, session, question_id, message.text)
        await message.answer("Ответ принят. Следующий вопрос:")
        sent_message = await message.answer(".")
        await go_to_next_question(message.bot, message.from_user.id, sent_message.message_id, state, session, next_question_id)
    else:
        await message.answer("Пожалуйста, воспользуйтесь кнопками для ответа.")


@router.callback_query(F.data == "back_to_previous_question")
async def back_handler(cb: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    current_data = await state.get_data()
    question_history = current_data.get("question_history", [])
    if not question_history:
        await cb.answer("Вы в самом начале, назад нельзя.", show_alert=True)
        return
        
    # Remove current question from history to get to the previous one
    question_history.pop()
    previous_question_id = question_history.pop() if question_history else 1 # Go to start if history is now empty
    
    await state.update_data(question_history=question_history)
    await show_question(cb.bot, cb.from_user.id, cb.message.message_id, state, session, previous_question_id)
    await cb.answer()
