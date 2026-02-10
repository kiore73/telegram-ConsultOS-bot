from aiogram import Bot, Router, Dispatcher
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from ..database.models import User, Payment
from ..states.booking import BookingFSM

router = Router()

async def on_payment_success(bot: Bot, session: AsyncSession, dispatcher: Dispatcher, payment: Payment):
    """
    Handles the logic after a successful payment.
    Starts the correct questionnaire or booking flow based on the user's tariff.
    """
    from ..services import questionnaire_service  # Lazy import
    
    user = payment.user
    state = FSMContext(storage=dispatcher.storage, key=str(user.telegram_id))

    tariff = user.tariff
    if not tariff:
        await bot.send_message(user.telegram_id, "Ошибка: не удалось определить ваш тариф.")
        return

    if tariff.name == "Повторная":
        await bot.send_message(user.telegram_id, "Спасибо за оплату! Давайте выберем время для вашей повторной консультации.")
        await state.set_state(BookingFSM.DATE_SELECT)
        await bot.send_message(user.telegram_id, "Пожалуйста, выберите доступный слот.")
        return

    pending_questionnaires = []
    user_data = await state.get_data()

    if tariff.name in ["Базовый", "Сопровождение"]:
        pending_questionnaires.append("basic")
    elif tariff.name == "Лайт":
        gender = user_data.get("gender")
        if gender == "male":
            pending_questionnaires.append("ayurved_m")
        elif gender == "female":
            pending_questionnaires.append("ayurved_j")

    if not pending_questionnaires:
        await bot.send_message(user.telegram_id, "Не найдено подходящих опросников для вашего тарифа.")
        return

    await state.update_data(pending_questionnaires=pending_questionnaires)

    message = await bot.send_message(user.telegram_id, "Начинаем...")

    await questionnaire_service.start_questionnaire(
        bot=bot,
        user_id=user.telegram_id,
        message_id=message.message_id,
        state=state,
        session=session
    )
