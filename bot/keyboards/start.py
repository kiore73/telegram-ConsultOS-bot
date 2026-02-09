from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from ..database.models import Tariff

async def get_tariffs_keyboard(session: AsyncSession) -> InlineKeyboardMarkup:
    """
    Fetches tariffs from the database and returns the keyboard with selection buttons.
    """
    tariffs_result = await session.execute(select(Tariff))
    tariffs = tariffs_result.scalars().all()
    
    keyboard_buttons = []
    for tariff in tariffs:
        button_text = f"{tariff.name} ({int(tariff.price)} RUB)"
        callback_data = f"tariff:{tariff.name}"
        keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
