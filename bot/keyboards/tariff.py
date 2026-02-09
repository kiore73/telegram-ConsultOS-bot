from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_gender_keyboard() -> InlineKeyboardMarkup:
    """Returns an inline keyboard for gender selection."""
    keyboard = [
        [
            InlineKeyboardButton(text="Мужчина", callback_data="select_gender:male"),
            InlineKeyboardButton(text="Женщина", callback_data="select_gender:female"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
