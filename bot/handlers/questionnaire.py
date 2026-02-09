import json
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from ..states.questionnaire import QuestionnaireFSM
...
from ..keyboards.booking import get_calendar_keyboard

router = Router()

@router.callback_query(QuestionnaireFSM.in_questionnaire, F.data.startswith("q_"))
async def answer_handler(cb: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    parts = cb.data.split('_')
    question_id = int(parts[1])
    option_index = int(parts[2])
    
    data = await state.get_data()
    current_q_title = data.get("current_questionnaire_title")
    q_cache = questionnaire_service.get_questionnaire_by_title(current_q_title)
    question = q_cache.get_question(question_id)
    answer_text = question.options[option_index]
    
    next_question_id = await process_answer(state, question_id, answer_text)

    if next_question_id:
        await show_question(cb.bot, cb.from_user.id, cb.message.message_id, state, session, next_question_id)
    else:
        await end_current_questionnaire_and_proceed(cb.bot, cb.from_user.id, cb.message.message_id, state, session)
    
    await cb.answer()
