import datetime
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..config import settings
from ..states.admin import AdminFSM
from ..keyboards.admin import get_admin_main_keyboard, get_admin_back_to_menu_keyboard, get_admin_calendar_keyboard, get_admin_time_slots_keyboard
from ..database.models import User, TimeSlot, Booking


router = Router()

# Admin filter
def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids_list


@router.message(Command("admin"))
async def admin_command_handler(message: types.Message, state: FSMContext):
    """
    Handles the /admin command, shows the admin panel.
    """
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для доступа к админ-панели.")
        return

    await state.set_state(AdminFSM.MENU)
    await message.answer("Добро пожаловать в админ-панель!", reply_markup=get_admin_main_keyboard())


@router.callback_query(AdminFSM.MENU, F.data == "admin_add_slot_start")
async def admin_add_slot_start(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Starts the process of adding a new time slot by showing the calendar.
    """
    await state.set_state(AdminFSM.ADD_SLOT_DATE)
    today = datetime.date.today()
    calendar_keyboard = await get_admin_calendar_keyboard(today, "admin_add_slot")
    await callback_query.message.edit_text(
        "Выберите дату для добавления слота:",
        reply_markup=calendar_keyboard
    )
    await callback_query.answer()


@router.callback_query(AdminFSM.ADD_SLOT_DATE, F.data.startswith("admin_add_slot_prev_month:"))
@router.callback_query(AdminFSM.ADD_SLOT_DATE, F.data.startswith("admin_add_slot_next_month:"))
async def admin_calendar_navigation_handler(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Handles navigation between months in the admin calendar.
    """
    _, action, date_str = callback_query.data.split(":")
    current_date = datetime.date.fromisoformat(date_str)

    if action == "prev_month":
        new_date = current_date.replace(day=1) - datetime.timedelta(days=1)
    elif action == "next_month":
        new_date = current_date.replace(day=28) + datetime.timedelta(days=4)
        new_date = new_date.replace(day=1)
    else:
        await callback_query.answer("Неизвестная команда.", show_alert=True)
        return

    calendar_keyboard = await get_admin_calendar_keyboard(new_date, "admin_add_slot")
    await callback_query.message.edit_reply_markup(reply_markup=calendar_keyboard)
    await callback_query.answer()


@router.callback_query(AdminFSM.ADD_SLOT_DATE, F.data.startswith("admin_add_slot_select_day:"))
async def admin_select_slot_date_handler(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Handles the selection of a date for a new slot and shows time options.
    """
    _, _, date_str = callback_query.data.split(":")
    selected_date = datetime.date.fromisoformat(date_str)

    await state.update_data(new_slot_date=selected_date.isoformat())
    await state.set_state(AdminFSM.ADD_SLOT_TIME)

    # Fetch existing slots for this date to mark them as unavailable
    existing_slots = (await session.execute(
        select(TimeSlot).where(TimeSlot.date == selected_date)
    )).scalars().all()
    
    time_keyboard = await get_admin_time_slots_keyboard(selected_date, existing_slots, "admin_add_slot")
    await callback_query.message.edit_text(
        f"Выбрана дата: {selected_date.strftime('%d %B %Y')}. Теперь выберите время:",
        reply_markup=time_keyboard
    )
    await callback_query.answer()


@router.callback_query(AdminFSM.ADD_SLOT_TIME, F.data.startswith("admin_add_slot_add_time:"))
async def admin_add_time_slot_handler(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Adds the selected time slot to the database.
    """
    _, _, date_str, time_str = callback_query.data.split(":")
    slot_date = datetime.date.fromisoformat(date_str)
    slot_time = datetime.time.fromisoformat(time_str)

    # Check if slot already exists (should be handled by keyboard, but good to double-check)
    existing_slot = (await session.execute(
        select(TimeSlot).where(TimeSlot.date == slot_date, TimeSlot.time == slot_time)
    )).scalar_one_or_none()
    
    if existing_slot:
        await callback_query.answer("Этот слот уже существует. Выберите другое время.", show_alert=True)
        return

    new_slot = TimeSlot(date=slot_date, time=slot_time, is_available=True)
    session.add(new_slot)
    await session.commit()

    await state.set_state(AdminFSM.MENU)
    await callback_query.message.edit_text(
        f"Новый слот на {slot_date.strftime('%Y-%m-%d')} в {slot_time.strftime('%H:%M')} успешно добавлен!",
        reply_markup=get_admin_main_keyboard()
    )
    await callback_query.answer()


@router.callback_query(AdminFSM.ADD_SLOT_TIME, F.data.startswith("admin_add_slot_back_to_date:"))
async def admin_add_slot_back_to_date_handler(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Returns from time selection to date selection in admin add slot flow.
    """
    _, _, date_str = callback_query.data.split(":")
    current_date = datetime.date.fromisoformat(date_str) # Get the month of the date that was previously selected

    await state.set_state(AdminFSM.ADD_SLOT_DATE)
    calendar_keyboard = await get_admin_calendar_keyboard(current_date, "admin_add_slot")
    await callback_query.message.edit_text(
        "Выберите дату для добавления слота:",
        reply_markup=calendar_keyboard
    )
    await callback_query.answer()


@router.callback_query(AdminFSM.MENU, F.data == "admin_list_bookings")
async def admin_list_bookings_handler(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Lists all current bookings.
    """
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет прав для доступа к админ-панели.", show_alert=True)
        return

    bookings_query = select(Booking).options(selectinload(Booking.user), selectinload(Booking.slot)).order_by(Booking.id.desc())
    result = await session.execute(bookings_query)
    bookings = result.scalars().all()

    if not bookings:
        await callback_query.message.edit_text(
            "Активных записей пока нет.",
            reply_markup=get_admin_back_to_menu_keyboard()
        )
        await callback_query.answer()
        return

    response_text = "<b>Активные записи:</b>\n\n"
    for booking in bookings:
        user_info = f"@{booking.user.username}" if booking.user.username else f"ID: {booking.user.telegram_id}"
        response_text += (
            f"Запись №{booking.id}\n"
            f"Пользователь: {user_info}\n"
            f"Дата: {booking.slot.date.strftime('%Y-%m-%d')}\n"
            f"Время: {booking.slot.time.strftime('%H:%M')}\n"
            f"Статус: {booking.status}\n"
            "----------------------------\n"
        )
    
    await callback_query.message.edit_text(
        response_text,
        reply_markup=get_admin_back_to_menu_keyboard()
    )
    await callback_query.answer()


@router.callback_query(AdminFSM.MENU, F.data == "admin_cancel_booking")
async def admin_cancel_booking_start(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Starts the process of canceling a booking.
    """
    # TODO: Implement cancellation logic. For now, just a placeholder.
    await callback_query.message.edit_text(
        "Функционал отмены записи пока не реализован.",
        reply_markup=get_admin_back_to_menu_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data == "admin_back_to_menu")
async def admin_back_to_menu_handler(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Returns to the main admin menu.
    """
    await state.set_state(AdminFSM.MENU)
    await callback_query.message.edit_text(
        "Вы в админ-панели.",
        reply_markup=get_admin_main_keyboard()
    )
    await callback_query.answer()