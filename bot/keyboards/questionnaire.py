from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from ..database.models import Question, QuestionLogic


async def get_question_keyboard(
    question: Question, 
    session: AsyncSession,
    selected_answers: List[str] = None
) -> InlineKeyboardMarkup:
    """
    Generates a keyboard for a given question, supporting single, multi, and photo types.
    """
    if selected_answers is None:
        selected_answers = []
    
    buttons = []
    
    if question.type == "single":
        # For single choice, get answers from the QuestionLogic table
        result = await session.execute(
            select(QuestionLogic).where(QuestionLogic.question_id == question.id)
        )
        answer_options = result.scalars().all()
        for option in answer_options:
            callback_data = f"answer:{question.id}:{option.answer_value}"
            buttons.append([InlineKeyboardButton(text=option.answer_value, callback_data=callback_data)])
            
    elif question.type == "multi":
        # For multi choice, get answers and mark selected ones
        result = await session.execute(
            select(QuestionLogic).where(QuestionLogic.question_id == question.id)
        )
        answer_options = result.scalars().all()
        for option in answer_options:
            text = option.answer_value
            if text in selected_answers:
                text = f"✅ {text}"
            
            callback_data = f"multi_answer:{question.id}:{option.answer_value}"
            buttons.append([InlineKeyboardButton(text=text, callback_data=callback_data)])
        
        # Add "Done" button for multi-choice
        buttons.append([InlineKeyboardButton(text="Готово", callback_data=f"multi_done:{question.id}")])

    elif question.type == "photo":
        # Add a "Skip" button for optional photo questions
        # We assume `allow_photo` in the model indicates it's a photo question,
        # and for now, we'll make them all skippable.
        buttons.append([InlineKeyboardButton(text="Пропустить", callback_data=f"skip_question:{question.id}")])

    # Add a 'Back' button for all types
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_previous_question")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
