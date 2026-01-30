from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..database.models import TimeSlot
import datetime


async def get_calendar_keyboard(session: AsyncSession) -> InlineKeyboardMarkup:
    """
    Generates a keyboard with available dates.
    """
    buttons = []
    # Query for distinct available dates
    result = await session.execute(
        select(TimeSlot.date)
        .where(TimeSlot.is_available == True)
        .distinct()
        .order_by(TimeSlot.date)
    )
    available_dates = result.scalars().all()

    for date in available_dates:
        callback_data = f"select_date:{date.isoformat()}"
        buttons.append([InlineKeyboardButton(text=date.strftime("%d %B %Y"), callback_data=callback_data)])
    
    # TODO: Add a 'Back' button to go back from booking
    # buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_...")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_time_keyboard(date: datetime.date, session: AsyncSession) -> InlineKeyboardMarkup:
    """
    Generates a keyboard with available time slots for a specific date.
    """
    buttons = []
    # Query for available time slots on the selected date
    result = await session.execute(
        select(TimeSlot)
        .where(TimeSlot.date == date, TimeSlot.is_available == True)
        .order_by(TimeSlot.time)
    )
    available_slots = result.scalars().all()

    for slot in available_slots:
        callback_data = f"select_time:{slot.id}"
        buttons.append([InlineKeyboardButton(text=slot.time.strftime("%H:%M"), callback_data=callback_data)])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад к выбору даты", callback_data="back_to_date_select")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
