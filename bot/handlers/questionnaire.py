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
    """
    Helper function to display a question.
    """
    result = await session.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()

    if question:
        # This is the final message, transition to booking
        if "Спасибо" in question.text:
            await state.set_state(BookingFSM.DATE_SELECT)
            calendar_keyboard = await get_calendar_keyboard(session)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="Спасибо за ответы! Теперь выберите удобную дату для консультации:",
                reply_markup=calendar_keyboard
            )
            return

        keyboard = await get_question_keyboard(question, session)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"Вопрос:\n\n{question.text}",
            reply_markup=keyboard
        )
        await state.update_data(current_question_id=question.id)
    else:
        # This case means the questionnaire is finished, transition to booking
        await state.set_state(BookingFSM.DATE_SELECT)
        calendar_keyboard = await get_calendar_keyboard(session)
        await bot.send_message(
            chat_id, 
            "Спасибо за ответы! Теперь выберите удобную дату для консультации:",
            reply_markup=calendar_keyboard
        )

@router.callback_query(F.data == "start_questionnaire")
async def start_questionnaire_handler(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Handles the 'Start Questionnaire' button press.
    """
    await state.set_state(QuestionnaireFSM.IN_QUESTIONNAIRE)
    await state.update_data(question_history=[], answers={})
    await show_question(callback_query.bot, callback_query.from_user.id, callback_query.message.message_id, state, session, question_id=1)
    await callback_query.answer()


async def process_answer(state: FSMContext, session: AsyncSession, user_id: int, question_id: int, answer_value: str):
    """
    Saves the answer and determines the next question.
    """
    # Save the answer
    current_data = await state.get_data()
    answers = current_data.get("answers", {})
    answers[str(question_id)] = answer_value
    
    # Update question history for the back button
    question_history = current_data.get("question_history", [])
    question_history.append(question_id)
    
    await state.update_data(answers=answers, question_history=question_history)

    # Find next question logic
    result = await session.execute(
        select(QuestionLogic).where(
            QuestionLogic.question_id == question_id,
            QuestionLogic.answer_value == answer_value
        )
    )
    logic = result.scalar_one_or_none()
    
    # If no specific logic, check for a generic "any" answer
    if not logic:
        result = await session.execute(
            select(QuestionLogic).where(
                QuestionLogic.question_id == question_id,
                QuestionLogic.answer_value == "любой"
            )
        )
        logic = result.scalar_one_or_none()

    if logic:
        return logic.next_question_id
    return None


@router.callback_query(F.data.startswith("answer:"))
async def answer_handler(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Handles answers from inline keyboard buttons.
    """
    _, question_id_str, answer_value = callback_query.data.split(":", 2)
    question_id = int(question_id_str)
    
    next_question_id = await process_answer(state, session, callback_query.from_user.id, question_id, answer_value)

    if next_question_id:
        await show_question(callback_query.bot, callback_query.from_user.id, callback_query.message.message_id, state, session, next_question_id)
    else:
        # No more questions, transition to booking
        await state.set_state(BookingFSM.DATE_SELECT)
        calendar_keyboard = await get_calendar_keyboard(session)
        await callback_query.message.edit_text(
            "Спасибо за ответы! Теперь выберите удобную дату для консультации:",
            reply_markup=calendar_keyboard
        )
        
    await callback_query.answer()


@router.message(QuestionnaireFSM.IN_QUESTIONNAIRE, F.text)
async def text_answer_handler(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handles text answers from the user.
    """
    current_data = await state.get_data()
    question_id = current_data.get("current_question_id")

    result = await session.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()

    if question and question.type == 'text':
        next_question_id = await process_answer(state, session, message.from_user.id, question_id, message.text)
        
        if next_question_id:
            # HACK: a bit of a hack to get a message_id to edit.
            # We need to find the bot's message to edit it. Let's just send a new one.
            await message.answer("Ответ принят. Следующий вопрос:")
            sent_message = await message.answer(".")
            await show_question(message.bot, message.from_user.id, sent_message.message_id, state, session, next_question_id)
        else:
            # No more questions, transition to booking
            await state.set_state(BookingFSM.DATE_SELECT)
            calendar_keyboard = await get_calendar_keyboard(session)
            await message.answer(
                "Спасибо за ответы! Теперь выберите удобную дату для консультации:",
                reply_markup=calendar_keyboard
            )

@router.callback_query(F.data == "back_to_previous_question")
async def back_handler(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Handles the 'Back' button.
    """
    current_data = await state.get_data()
    question_history = current_data.get("question_history", [])

    if not question_history:
        await callback_query.answer("Вы в самом начале, назад нельзя.", show_alert=True)
        return

    previous_question_id = question_history.pop()
    await state.update_data(question_history=question_history)
    
    await show_question(callback_query.bot, callback_query.from_user.id, callback_query.message.message_id, state, session, previous_question_id)
    await callback_query.answer()
