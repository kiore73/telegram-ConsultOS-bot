import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..states.payment import PaymentFSM
from ..config import settings
from ..database.models import User, Payment
from ..services.yookassa_service import YooKassaService

router = Router()


@router.callback_query(F.data == "proceed_to_payment")
async def proceed_to_payment_handler(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Handles the 'Proceed to Payment' button press.
    Creates a direct YooKassa payment and sends the link to the user.
    """
    user_id = callback_query.from_user.id
    
    # Check if user has already paid
    user = (await session.execute(select(User).where(User.telegram_id == user_id))).scalar_one_or_none()
    if user and user.has_paid:
        await callback_query.answer("Вы уже оплатили услугу.", show_alert=True)
        return

    await state.set_state(PaymentFSM.WAIT_PAYMENT)

    # Instantiate YooKassa Service (credentials now from settings directly)
    yookassa_service = YooKassaService()

    # Define payment details
    amount = settings.SERVICE_PRICE
    description = "Оплата консультации"
    metadata = {"user_id": user_id, "username": callback_query.from_user.username}

    payment_details = await yookassa_service.create_payment(
        amount=amount,
        currency="RUB",
        description=description,
        metadata=metadata
    )

    if payment_details and "confirmation_url" in payment_details:
        payment_id = payment_details["id"]
        confirmation_url = payment_details["confirmation_url"]

        # Create a pending payment record in the database
        new_payment = Payment(
            user_id=user.id,
            amount=amount,
            status="pending",
            provider_charge_id=payment_id
        )
        session.add(new_payment)
        await session.commit()
        
        # Create keyboard with only payment link
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="➡️ Оплатить", url=confirmation_url)]
        ])
        
        await callback_query.message.edit_text(
            "Нажмите кнопку ниже, чтобы перейти к оплате. Подтверждение произойдет автоматически после успешной оплаты.",
            reply_markup=keyboard
        )
    else:
        await callback_query.message.edit_text(
            "Не удалось создать ссылку на оплату. Попробуйте позже или свяжитесь с поддержкой."
        )
    
    await callback_query.answer()
