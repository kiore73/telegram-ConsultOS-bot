from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def get_tariffs_keyboard():
    """
    Returns the keyboard with tariff selection buttons.
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Базовый (8000 RUB)", callback_data="tariff:basic:8000")
            ],
            [
                InlineKeyboardButton(text="Сопровождение (20000 RUB)", callback_data="tariff:support:20000")
            ],
            [
                InlineKeyboardButton(text="Повторная консультация (5000 RUB)", callback_data="tariff:repeat:5000")
            ],
            [
                InlineKeyboardButton(text="Лайт консультация (3000 RUB)", callback_data="tariff:lite:3000")
            ]
        ]
    )
    return keyboard
