from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import datetime

from ..states.booking import BookingFSM
from ..database.models import TimeSlot, Booking, User
from ..keyboards.booking import get_time_keyboard, get_calendar_keyboard

router = Router()


@router.callback_query(BookingFSM.DATE_SELECT, F.data.startswith("select_date:"))
async def select_date_handler(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Handles date selection.
    """
    selected_date_str = callback_query.data.split(":")[1]
    selected_date = datetime.date.fromisoformat(selected_date_str)

    await state.update_data(selected_date=selected_date_str)
    await state.set_state(BookingFSM.TIME_SELECT)

    time_keyboard = await get_time_keyboard(selected_date, session)
    await callback_query.message.edit_text(
        f"Вы выбрали дату: {selected_date.strftime('%d %B %Y')}. Теперь выберите удобное время:",
        reply_markup=time_keyboard
    )
    await callback_query.answer()


@router.callback_query(BookingFSM.TIME_SELECT, F.data.startswith("select_time:"))
async def select_time_handler(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Handles time slot selection and confirms the booking.
    """
    slot_id = int(callback_query.data.split(":")[1])

    # Find user and slot
    user_result = await session.execute(select(User).where(User.telegram_id == callback_query.from_user.id))
    user = user_result.scalar_one()
    
    slot_result = await session.execute(select(TimeSlot).where(TimeSlot.id == slot_id))
    slot = slot_result.scalar_one()

    if slot and slot.is_available and user:
        # Mark slot as unavailable and create booking
        slot.is_available = False
        new_booking = Booking(
            user_id=user.id,
            slot_id=slot.id,
            status="confirmed"
        )
        session.add(new_booking)
        await session.commit()

        await state.clear()
        await callback_query.message.edit_text(
            f"Отлично! Вы успешно записаны на {slot.date.strftime('%d %B %Y')} в {slot.time.strftime('%H:%M')}.\n\n"
            "В ближайшее время с вами свяжется администратор."
        )
    else:
        await callback_query.message.edit_text("К сожалению, этот слот уже занят. Пожалуйста, выберите другой.")
        # Reshow the calendar
        calendar_keyboard = await get_calendar_keyboard(session)
        await callback_query.message.answer("Выберите другую дату:", reply_markup=calendar_keyboard)
        await state.set_state(BookingFSM.DATE_SELECT)
        
    await callback_query.answer()


@router.callback_query(BookingFSM.TIME_SELECT, F.data == "back_to_date_select")
async def back_to_date_select_handler(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Handles the 'Back' button press from the time selection view.
    """
    await state.set_state(BookingFSM.DATE_SELECT)
    calendar_keyboard = await get_calendar_keyboard(session)
    await callback_query.message.edit_text(
        "Выберите удобную дату для консультации:",
        reply_markup=calendar_keyboard
    )
    await callback_query.answer()
