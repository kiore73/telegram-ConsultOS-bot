from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List

from ..services.questionnaire_service import CachedQuestion


def get_question_keyboard(
    question: CachedQuestion, 
    selected_answers: List[str] = None
) -> InlineKeyboardMarkup:
    """
    Generates a keyboard for a given cached question. This function is now synchronous
    and does not require a database session.
    """
    if selected_answers is None:
        selected_answers = []
    
    buttons = []
    
    if question.type == "single":
        # For single choice, get answers from the pre-loaded options
        for option_text in question.options:
            callback_data = f"q_answer:{question.id}:{option_text}"
            buttons.append([InlineKeyboardButton(text=option_text, callback_data=callback_data)])
            
    elif question.type == "multi":
        # For multi choice, get answers and mark selected ones
        for option_text in question.options:
            text = option_text
            if text in selected_answers:
                text = f"✅ {text}"
            
            callback_data = f"q_multi_select:{question.id}:{option_text}"
            buttons.append([InlineKeyboardButton(text=text, callback_data=callback_data)])
        
        # Add "Done" button for multi-choice
        buttons.append([InlineKeyboardButton(text="Готово", callback_data=f"multi_done:{question.id}")])

    elif question.type == "photo":
        # Add a "Skip" button for optional photo questions
        buttons.append([InlineKeyboardButton(text="Пропустить", callback_data=f"skip_question:{question.id}")])

    # Add a 'Back' button for all types
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_previous_question")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)