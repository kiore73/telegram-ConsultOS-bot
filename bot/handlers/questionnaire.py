# Refactored for performance: uses QuestionnaireService cache instead of DB queries.
import json
import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from ..states.questionnaire import QuestionnaireFSM
from ..states.booking import BookingFSM
from ..services.questionnaire_service import QuestionnaireService
from ..keyboards.questionnaire import get_question_keyboard
from ..keyboards.booking import get_calendar_keyboard

router = Router()


async def show_question(
    bot: Bot, 
    chat_id: int, 
    message_id: int, 
    state: FSMContext, 
    questionnaire_service: QuestionnaireService, 
    session: AsyncSession, # Keep session for calendar keyboard
    question_id: int
):
    """ Helper function to display a question using the cache. """
    q_cache = questionnaire_service.get_cache()
    question = q_cache.get_question(question_id)

    if not question:
        await bot.send_message(chat_id, "Опросник завершен или произошла ошибка.")
        await state.clear()
        return

    # New, robust way to detect the final "thank you" slide
    if question.type == 'final':
        await state.set_state(BookingFSM.DATE_SELECT)
        calendar_keyboard = await get_calendar_keyboard(session)
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text=f"{question.text}\n\nТеперь выберите удобную дату для консультации:",
            reply_markup=calendar_keyboard
        )
        return
    
    current_data = await state.get_data()
    selected_answers = current_data.get(f"multi_answers_{question_id}", [])
    
    # Keyboard generation now uses cached data, no session needed
    keyboard = get_question_keyboard(question, selected_answers)
    
    await bot.edit_message_text(
        chat_id=chat_id, message_id=message_id,
        text=f"Вопрос:\n\n{question.text}",
        reply_markup=keyboard
    )
    await state.update_data(current_question_id=question.id)


async def process_answer(state: FSMContext, questionnaire_service: QuestionnaireService, question_id: int, answer_value):
    """ Saves the answer to FSM and determines the next question from cache. """
    current_data = await state.get_data()
    answers = current_data.get("answers", {})
    
    q_cache = questionnaire_service.get_cache()
    question = q_cache.get_question(question_id)
    
    # Robustly find and store the gender question's ID when it's answered
    if "Укажите ваш пол" in question.text:
        await state.update_data(gender_question_id=question_id)

    logic_answer_value = answer_value
    if question.type == 'multi':
        answers[str(question_id)] = json.dumps(answer_value, ensure_ascii=False)
        logic_answer_value = "любой" # Branching for multi is generic
    else:
        answers[str(question_id)] = answer_value

    question_history = current_data.get("question_history", [])
    if question_id not in question_history:
        question_history.append(question_id)
    
    await state.update_data(answers=answers, question_history=question_history)
    
    return q_cache.get_next_question_id(question_id, logic_answer_value)


async def go_to_next_question(
    bot: Bot, 
    chat_id: int, 
    message_id: int, 
    state: FSMContext, 
    questionnaire_service: QuestionnaireService, 
    session: AsyncSession,
    next_question_id: int
):
    """ 
    Transitions to the next question or ends the questionnaire.
    Handles internal branching nodes.
    """
    q_cache = questionnaire_service.get_cache()
    
    # Handle internal branching node for gender
    if next_question_id and q_cache.get_question(next_question_id).type == 'internal':
        current_data = await state.get_data()
        answers = current_data.get("answers", {})
        
        # Robustly get the gender question's ID from the state
        gender_q_id = current_data.get("gender_question_id")
        
        gender_answer = answers.get(str(gender_q_id)) if gender_q_id else None
        
        # Determine the next step based on gender
        final_next_id = q_cache.get_next_question_id(next_question_id, gender_answer)
        logging.info(f"Internal branch: gender_answer='{gender_answer}', redirecting to QID {final_next_id}")

        # Recursively call itself to proceed to the correct next question
        await go_to_next_question(bot, chat_id, message_id, state, questionnaire_service, session, final_next_id)
        return

    if next_question_id:
        await show_question(bot, chat_id, message_id, state, questionnaire_service, session, next_question_id)
    else:
        # End of questionnaire, transition to booking
        await state.set_state(BookingFSM.DATE_SELECT)
        calendar_keyboard = await get_calendar_keyboard(session)
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text="Спасибо за ответы! Теперь выберите удобную дату для консультации:",
            reply_markup=calendar_keyboard
        )


@router.callback_query(F.data == "start_questionnaire")
async def start_questionnaire_handler(cb: types.CallbackQuery, state: FSMContext, questionnaire_service: QuestionnaireService, session: AsyncSession):
    await state.set_state(QuestionnaireFSM.IN_QUESTIONNAIRE)
    await state.update_data(question_history=[], answers={})
    
    start_question_id = questionnaire_service.get_cache().start_question_id
    if start_question_id:
        await show_question(cb.bot, cb.from_user.id, cb.message.message_id, state, questionnaire_service, session, start_question_id)
    else:
        await cb.message.edit_text("Опросник еще не настроен.")
    await cb.answer()


# --- New, Simplified Handlers ---

@router.callback_query(F.data.startswith("q_answer:"))
async def new_answer_handler(cb: types.CallbackQuery, state: FSMContext, questionnaire_service: QuestionnaireService, session: AsyncSession):
    """ Handles single-choice answers from the cached questionnaire. """
    _, q_id_str, answer_text = cb.data.split(":", 2)
    question_id = int(q_id_str)
    
    next_question_id = await process_answer(state, questionnaire_service, question_id, answer_text)
    await go_to_next_question(cb.bot, cb.from_user.id, cb.message.message_id, state, questionnaire_service, session, next_question_id)
    await cb.answer()


@router.callback_query(F.data.startswith("q_multi_select:"))
async def new_multi_select_handler(cb: types.CallbackQuery, state: FSMContext, questionnaire_service: QuestionnaireService, session: AsyncSession):
    """ Handles a multi-choice answer selection. """
    _, q_id_str, answer_text = cb.data.split(":", 2)
    question_id = int(q_id_str)
    
    current_data = await state.get_data()
    selected_key = f"multi_answers_{question_id}"
    selected_for_q = current_data.get(selected_key, [])
    
    if answer_text in selected_for_q:
        selected_for_q.remove(answer_text)
    else:
        selected_for_q.append(answer_text)
        
    await state.update_data({selected_key: selected_for_q})
    # Re-show the same question with updated keyboard
    await show_question(cb.bot, cb.from_user.id, cb.message.message_id, state, questionnaire_service, session, question_id)
    await cb.answer()


@router.callback_query(F.data.startswith("multi_done:"))
async def multi_done_handler(cb: types.CallbackQuery, state: FSMContext, questionnaire_service: QuestionnaireService, session: AsyncSession):
    _, q_id_str = cb.data.split(":", 1)
    question_id = int(q_id_str)
    
    current_data = await state.get_data()
    selected_answers = current_data.get(f"multi_answers_{question_id}", [])
    
    next_question_id = await process_answer(state, questionnaire_service, question_id, selected_answers)
    await go_to_next_question(cb.bot, cb.from_user.id, cb.message.message_id, state, questionnaire_service, session, next_question_id)
    await cb.answer()


@router.message(QuestionnaireFSM.IN_QUESTIONNAIRE, F.photo)
async def photo_answer_handler(message: types.Message, state: FSMContext, questionnaire_service: QuestionnaireService, session: AsyncSession):
    current_data = await state.get_data()
    question_id = current_data.get("current_question_id")
    
    question = questionnaire_service.get_cache().get_question(question_id)

    if question and question.type == 'photo':
        photo_file_id = message.photo[-1].file_id
        next_question_id = await process_answer(state, questionnaire_service, question_id, photo_file_id)
        
        await message.answer("Фото получено. Следующий вопрос:")
        sent_message = await message.answer(".")
        await go_to_next_question(message.bot, message.from_user.id, sent_message.message_id, state, questionnaire_service, session, next_question_id)
    else:
        await message.answer("Пожалуйста, ответьте на текущий вопрос или отправьте фото, если это требуется.")


@router.callback_query(F.data.startswith("skip_question:"))
async def skip_question_handler(cb: types.CallbackQuery, state: FSMContext, questionnaire_service: QuestionnaireService, session: AsyncSession):
    _, q_id_str = cb.data.split(":", 1)
    next_question_id = await process_answer(state, questionnaire_service, int(q_id_str), "skipped")
    await go_to_next_question(cb.bot, cb.from_user.id, cb.message.message_id, state, questionnaire_service, session, next_question_id)
    await cb.answer()


@router.message(QuestionnaireFSM.IN_QUESTIONNAIRE, F.text)
async def text_answer_handler(message: types.Message, state: FSMContext, questionnaire_service: QuestionnaireService, session: AsyncSession):
    current_data = await state.get_data()
    question_id = current_data.get("current_question_id")

    question = questionnaire_service.get_cache().get_question(question_id)

    if question and question.type == 'text':
        next_question_id = await process_answer(state, questionnaire_service, question_id, message.text)
        await message.answer("Ответ принят. Следующий вопрос:")
        sent_message = await message.answer(".")
        await go_to_next_question(message.bot, message.from_user.id, sent_message.message_id, state, questionnaire_service, session, next_question_id)
    else:
        await message.answer("Пожалуйста, воспользуйтесь кнопками для ответа.")


@router.callback_query(F.data == "back_to_previous_question")
async def back_handler(cb: types.CallbackQuery, state: FSMContext, questionnaire_service: QuestionnaireService, session: AsyncSession):
    current_data = await state.get_data()
    question_history = current_data.get("question_history", [])
    if not question_history:
        await cb.answer("Вы в самом начале, назад нельзя.", show_alert=True)
        return
        
    # Remove current question from history to get to the previous one
    question_history.pop()
    previous_question_id = question_history.pop() if question_history else questionnaire_service.get_cache().start_question_id
    
    await state.update_data(question_history=question_history)
    await show_question(cb.bot, cb.from_user.id, cb.message.message_id, state, questionnaire_service, session, previous_question_id)
    await cb.answer()