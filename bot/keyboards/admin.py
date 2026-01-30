from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    """
    Generates the main admin keyboard.
    """
    buttons = [
        [
            InlineKeyboardButton(text="➕ Добавить слот", callback_data="admin_add_slot"),
        ],
        [
            InlineKeyboardButton(text="👀 Список записей", callback_data="admin_list_bookings"),
        ],
        [
            InlineKeyboardButton(text="❌ Отменить запись", callback_data="admin_cancel_booking"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_back_keyboard() -> InlineKeyboardMarkup:
    """
    Generates a simple keyboard with a 'Back' button for admin sub-menus.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_back_to_menu")]
    ])