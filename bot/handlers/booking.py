from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import datetime
import json # For formatting answers

from ..states.booking import BookingFSM
from ..states.questionnaire import QuestionnaireFSM # Import QuestionnaireFSM to get answers
from ..config import settings
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

        # Get questionnaire answers
        fsm_data = await state.get_data()
        questionnaire_answers = fsm_data.get("answers", {})
        formatted_answers = "\n".join([f"- {k}: {v}" for k, v in questionnaire_answers.items()])

        await state.clear() # Clear state after successful booking
        await callback_query.message.edit_text(
            f"Отлично! Вы успешно записаны на {slot.date.strftime('%d %B %Y')} в {slot.time.strftime('%H:%M')}.\n\n"
            "В ближайшее время с вами свяжется администратор."
        )

        # Send notification to admins
        admin_notification_text = (
            f"📅 <b>Новая запись!</b>\n\n"
            f"Пользователь: {callback_query.from_user.full_name} (@{callback_query.from_user.username})\n"
            f"ID: <code>{callback_query.from_user.id}</code>\n"
            f"На дату: {slot.date.strftime('%Y-%m-%d')}\n"
            f"На время: {slot.time.strftime('%H:%M')}\n"
            f"Ответы на опросник:\n{formatted_answers}"
        )
        for admin_id in settings.ADMIN_IDS:
            try:
                await callback_query.bot.send_message(admin_id, admin_notification_text)
            except Exception as e:
                import logging
                logging.error(f"Failed to send booking notification to admin {admin_id}: {e}")

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
