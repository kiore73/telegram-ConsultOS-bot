from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
from typing import List, Optional

from ..database.models import TimeSlot


def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    """
    Generates the main admin keyboard.
    """
    buttons = [
        [
            InlineKeyboardButton(text="➕ Добавить слот", callback_data="admin_add_slot_start"),
        ],
        [
            InlineKeyboardButton(text="👀 Список записей", callback_data="admin_list_bookings"),
        ],
        [
            InlineKeyboardButton(text="❌ Отменить запись", callback_data="admin_cancel_booking"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Generates a simple keyboard with a 'Back to Admin Menu' button.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_back_to_menu")]
    ])


# --- Admin Calendar/Time Slot Keyboards ---

async def get_admin_calendar_keyboard(current_date: datetime.date, prefix: str) -> InlineKeyboardMarkup:
    """
    Generates a calendar-like keyboard for admin to select a date.
    prefix: used for callback data, e.g., 'admin_add_slot_date'
    """
    keyboard = []
    
    # Header with current month and year
    keyboard.append([
        InlineKeyboardButton(text="<", callback_data=f"{prefix}:prev_month:{current_date.isoformat()}"),
        InlineKeyboardButton(text=current_date.strftime("%B %Y"), callback_data=f"{prefix}:current_month:{current_date.isoformat()}"),
        InlineKeyboardButton(text=">", callback_data=f"{prefix}:next_month:{current_date.isoformat()}"),
    ])

    # Weekday headers
    keyboard.append([
        InlineKeyboardButton(text="Пн", callback_data="ignore"),
        InlineKeyboardButton(text="Вт", callback_data="ignore"),
        InlineKeyboardButton(text="Ср", callback_data="ignore"),
        InlineKeyboardButton(text="Чт", callback_data="ignore"),
        InlineKeyboardButton(text="Пт", callback_data="ignore"),
        InlineKeyboardButton(text="Сб", callback_data="ignore"),
        InlineKeyboardButton(text="Вс", callback_data="ignore"),
    ])

    # Days of the month
    first_day_of_month = current_date.replace(day=1)
    day_of_week = first_day_of_month.weekday() # Monday is 0, Sunday is 6

    row = [InlineKeyboardButton(text=" ", callback_data="ignore")] * day_of_week
    for day in range(1, (current_date.replace(month=current_date.month % 12 + 1, day=1) - datetime.timedelta(days=1)).day + 1):
        date_obj = current_date.replace(day=day)
        if len(row) == 7:
            keyboard.append(row)
            row = []
        
        callback_data = f"{prefix}:select_day:{date_obj.isoformat()}"
        row.append(InlineKeyboardButton(text=str(day), callback_data=callback_data))
    
    if row: # Add last row if not empty
        keyboard.append(row + [InlineKeyboardButton(text=" ", callback_data="ignore")] * (7 - len(row)))

    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_menu")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def get_admin_time_slots_keyboard(selected_date: datetime.date, existing_slots: List[TimeSlot], prefix: str) -> InlineKeyboardMarkup:
    """
    Generates a keyboard with predefined time options for admin to add a slot.
    Shows existing slots as unavailable.
    """
    keyboard = []
    
    # Predefined time options
    times = [
        datetime.time(9, 0), datetime.time(10, 0), datetime.time(11, 0), datetime.time(12, 0),
        datetime.time(13, 0), datetime.time(14, 0), datetime.time(15, 0), datetime.time(16, 0),
        datetime.time(17, 0), datetime.time(18, 0)
    ]

    existing_times = {slot.time for slot in existing_slots}

    row = []
    for time_option in times:
        button_text = time_option.strftime("%H:%M")
        callback_data = f"{prefix}_add_time:{selected_date.isoformat()}:{time_option.isoformat()}"
        
        if time_option in existing_times:
            button_text = f"❌ {button_text}" # Mark as unavailable
            callback_data = "ignore" # Make non-clickable

        row.append(InlineKeyboardButton(text=button_text, callback_data=callback_data))
        if len(row) == 4: # 4 buttons per row
            keyboard.append(row)
            row = []
    
    if row: # Add remaining buttons
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton(text="⬅️ Назад к выбору даты", callback_data=f"{prefix}_back_to_date:{selected_date.isoformat()}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_back_to_menu")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)