import datetime
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from ..config import settings
from ..states.admin import AdminFSM
from ..keyboards.admin import get_admin_main_keyboard, get_admin_back_keyboard
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


@router.callback_query(AdminFSM.MENU, F.data == "admin_add_slot")
async def admin_add_slot_start(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Starts the process of adding a new time slot.
    """
    await state.set_state(AdminFSM.ADD_SLOT_DATE)
    await callback_query.message.edit_text(
        "Введите дату для нового слота в формате ГГГГ-ММ-ДД (например, 2026-01-30):",
        reply_markup=get_admin_back_keyboard()
    )
    await callback_query.answer()


@router.message(AdminFSM.ADD_SLOT_DATE, F.text)
async def admin_add_slot_date_received(message: types.Message, state: FSMContext):
    """
    Receives the date for the new slot and asks for time.
    """
    try:
        slot_date = datetime.date.fromisoformat(message.text)
        await state.update_data(new_slot_date=slot_date)
        await state.set_state(AdminFSM.ADD_SLOT_TIME)
        await message.answer(
            f"Дата {slot_date.strftime('%Y-%m-%d')} принята. Теперь введите время в формате ЧЧ:ММ (например, 14:00):",
            reply_markup=get_admin_back_keyboard()
        )
    except ValueError:
        await message.answer(
            "Неверный формат даты. Пожалуйста, введите дату в формате ГГГГ-ММ-ДД.",
            reply_markup=get_admin_back_keyboard()
        )


@router.message(AdminFSM.ADD_SLOT_TIME, F.text)
async def admin_add_slot_time_received(message: types.Message, state: FSMContext, session: AsyncSession):
    """
    Receives the time for the new slot, creates it, and confirms.
    """
    try:
        slot_time = datetime.time.fromisoformat(message.text)
        data = await state.get_data()
        slot_date = data["new_slot_date"]

        # Check if slot already exists
        existing_slot = await session.execute(
            select(TimeSlot).where(TimeSlot.date == slot_date, TimeSlot.time == slot_time)
        )
        if existing_slot.scalar_one_or_none():
            await message.answer(
                f"Слот на {slot_date.strftime('%Y-%m-%d')} в {slot_time.strftime('%H:%M')} уже существует.",
                reply_markup=get_admin_back_keyboard()
            )
            return

        new_slot = TimeSlot(date=slot_date, time=slot_time, is_available=True)
        session.add(new_slot)
        await session.commit()

        await state.set_state(AdminFSM.MENU)
        await message.answer(
            f"Новый слот на {slot_date.strftime('%Y-%m-%d')} в {slot_time.strftime('%H:%M')} успешно добавлен!",
            reply_markup=get_admin_main_keyboard()
        )
    except ValueError:
        await message.answer(
            "Неверный формат времени. Пожалуйста, введите время в формате ЧЧ:ММ.",
            reply_markup=get_admin_back_keyboard()
        )


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
            reply_markup=get_admin_back_keyboard()
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
        reply_markup=get_admin_back_keyboard()
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
        reply_markup=get_admin_back_keyboard()
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