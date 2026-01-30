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

    # Instantiate YooKassa Service
    yookassa_service = YooKassaService(
        shop_id=settings.YOOKASSA_SHOP_ID.get_secret_value(),
        secret_key=settings.YOOKASSA_SECRET_KEY.get_secret_value(),
        configured_return_url=settings.YOOKASSA_RETURN_URL
    )

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
        
        # Create keyboard with payment link and check button
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="➡️ Оплатить", url=confirmation_url)],
            [types.InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_payment:{payment_id}")]
        ])
        
        await callback_query.message.edit_text(
            "Нажмите кнопку ниже, чтобы перейти к оплате. После успешной оплаты вернитесь и нажмите 'Я оплатил'.",
            reply_markup=keyboard
        )
    else:
        await callback_query.message.edit_text(
            "Не удалось создать ссылку на оплату. Попробуйте позже или свяжитесь с поддержкой."
        )
    
    await callback_query.answer()


@router.callback_query(F.data.startswith("check_payment:"))
async def check_payment_handler(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Handles the 'I have paid' button press.
    Checks the payment status with YooKassa API.
    """
    yookassa_payment_id = callback_query.data.split(":")[1]
    user_id = callback_query.from_user.id
    await callback_query.answer("Проверяем статус вашего платежа...")

    # Instantiate YooKassa Service
    yookassa_service = YooKassaService(
        shop_id=settings.YOOKASSA_SHOP_ID.get_secret_value(),
        secret_key=settings.YOOKASSA_SECRET_KEY.get_secret_value(),
        configured_return_url=settings.YOOKASSA_RETURN_URL
    )

    payment_info = await yookassa_service.get_payment_info(yookassa_payment_id)

    if payment_info and payment_info.get("status") == "succeeded":
        # Find user and payment record
        user = (await session.execute(select(User).where(User.telegram_id == user_id))).scalar_one()
        payment = (await session.execute(select(Payment).where(Payment.provider_charge_id == yookassa_payment_id))).scalar_one()

        if user and payment:
            # Update database
            user.has_paid = True
            payment.status = "success"
            await session.commit()

            await state.set_state(PaymentFSM.PAYMENT_SUCCESS)

            # Send success message to user
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="Перейти к опроснику", callback_data="start_questionnaire")]
            ])
            await callback_query.message.edit_text(
                f"Оплата прошла успешно! Теперь вы можете перейти к опроснику.",
                reply_markup=keyboard
            )

            # Send notification to admins
            admin_notification_text = (
                f"💰 <b>Новая успешная оплата (YooKassa API)!</b>\n\n"
                f"Пользователь: {callback_query.from_user.full_name} (@{callback_query.from_user.username})\n"
                f"ID: <code>{user_id}</code>\n"
                f"Сумма: {payment_info['amount_value']} {payment_info['amount_currency']}\n"
                f"YooKassa Payment ID: <code>{yookassa_payment_id}</code>"
            )
            for admin_id in settings.ADMIN_IDS:
                try:
                    await callback_query.bot.send_message(admin_id, admin_notification_text)
                except Exception as e:
                    logging.error(f"Failed to send payment notification to admin {admin_id}: {e}")
        else:
            await callback_query.message.edit_text("Произошла внутренняя ошибка. Свяжитесь с поддержкой.")

    else:
        await callback_query.message.answer(
            "Ваша оплата еще не подтверждена. Пожалуйста, убедитесь, что вы завершили платеж, и попробуйте проверить снова через минуту."
        )

