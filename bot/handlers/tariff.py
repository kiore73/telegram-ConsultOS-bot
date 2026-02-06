from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..states.payment import PaymentFSM
from ..database.models import User, Payment
from ..services.yookassa_service import YooKassaService

router = Router()

@router.callback_query(F.data.startswith("tariff:"))
async def select_tariff_handler(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Handles the tariff selection, initiates payment, and sends the payment link.
    """
    user_id = callback_query.from_user.id
    
    # Check if user has already paid
    user = (await session.execute(select(User).where(User.telegram_id == user_id))).scalar_one_or_none()
    if user and user.has_paid:
        await callback_query.answer("Вы уже оплатили услугу.", show_alert=True)
        return

    # Parse tariff info from callback_data
    _, tariff_name, price_str = callback_query.data.split(":")
    price = int(price_str)

    await state.set_state(PaymentFSM.WAIT_PAYMENT)
    await state.update_data(tariff_name=tariff_name, price=price)

    # Instantiate YooKassa Service
    yookassa_service = YooKassaService()

    # Define payment details
    description = f"Оплата тарифа '{tariff_name}'"
    metadata = {"user_id": user_id, "username": callback_query.from_user.username, "tariff": tariff_name}

    payment_details = await yookassa_service.create_payment(
        amount=price,
        currency="RUB",
        description=description,
        metadata=metadata
    )

    if payment_details and "confirmation_url" in payment_details:
        payment_id = payment_details["id"]
        confirmation_url = payment_details["confirmation_url"]

        # Create a pending payment record
        new_payment = Payment(
            user_id=user.id,
            amount=price,
            status="pending",
            provider_charge_id=payment_id
        )
        session.add(new_payment)
        
        # Update user's tariff
        user.tariff = tariff_name
        session.add(user)

        await session.commit()
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="➡️ Оплатить", url=confirmation_url)]
        ])
        
        await callback_query.message.edit_text(
            f"Вы выбрали тариф '{tariff_name}'.\n"
            "Нажмите кнопку ниже, чтобы перейти к оплате. Подтверждение произойдет автоматически.",
            reply_markup=keyboard
        )
    else:
        await callback_query.message.edit_text(
            "Не удалось создать ссылку на оплату. Попробуйте позже или свяжитесь с поддержкой."
        )
    
    await callback_query.answer()
