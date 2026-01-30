from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database.models import Question, QuestionLogic


async def get_question_keyboard(question: Question, session: AsyncSession) -> InlineKeyboardMarkup:
    """
    Generates a keyboard for a given question.
    """
    buttons = []
    if question.type == "single":
        # For single choice, get answers from the QuestionLogic table
        result = await session.execute(
            select(QuestionLogic).where(QuestionLogic.question_id == question.id)
        )
        answer_options = result.scalars().all()
        for option in answer_options:
            # We use a prefix to identify question answers
            callback_data = f"answer:{question.id}:{option.answer_value}"
            buttons.append([InlineKeyboardButton(text=option.answer_value, callback_data=callback_data)])
    
    # TODO: Add logic for 'multi', 'text', 'photo' question types.
    # For now, they won't have a specific keyboard, user will just type the answer.

    # Add a 'Back' button
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_previous_question")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
