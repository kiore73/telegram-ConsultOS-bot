from aiogram import Router, F, types
from aiogram.types import Message, PreCheckoutQuery, SuccessfulPayment
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..states.payment import PaymentFSM
from ..config import settings
from ..database.models import User, Payment

router = Router()


@router.callback_query(F.data == "proceed_to_payment")
async def proceed_to_payment_handler(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Handles the 'Proceed to Payment' button press.
    Sends an invoice to the user.
    """
    # Check if user has already paid
    result = await session.execute(select(User).where(User.telegram_id == callback_query.from_user.id))
    user = result.scalar_one_or_none()
    if user and user.has_paid:
        await callback_query.answer("Вы уже оплатили услугу.", show_alert=True)
        return

    await state.set_state(PaymentFSM.WAIT_PAYMENT)

    # TODO: Replace with actual product details and price
    PRICE = types.LabeledPrice(label="Консультация", amount=1000 * 100)  # Amount in kopecks (e.g., 1000 RUB)

    await callback_query.bot.send_invoice(
        chat_id=callback_query.from_user.id,
        title="Оплата услуги",
        description="Описание услуги для оплаты",
        payload="payment_for_consultation",  # Internal bot payload
        provider_token=settings.YUKASSA_TOKEN.get_secret_value(),
        currency="RUB",
        prices=[PRICE],
        start_parameter="consultos-bot-payment",
    )
    await callback_query.answer()


@router.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: PreCheckoutQuery):
    """
    Handles pre-checkout queries. This is where you confirm you can fulfill the order.
    """
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handles successful payments and saves the data to the database.
    """
    payment_info = message.successful_payment
    
    # Find the user
    result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
    user = result.scalar_one_or_none()

    if user:
        # Update user status
        user.has_paid = True

        # Create payment record
        new_payment = Payment(
            user_id=user.id,
            amount=payment_info.total_amount / 100,
            status="success",
            telegram_charge_id=payment_info.telegram_payment_charge_id,
            provider_charge_id=payment_info.provider_payment_charge_id,
        )
        session.add(new_payment)
        
        await session.commit()
        
        await state.set_state(PaymentFSM.PAYMENT_SUCCESS)

        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="Перейти к опроснику", callback_data="start_questionnaire")]
            ]
        )
        await message.answer(
            f"Оплата на сумму {payment_info.total_amount // 100} {payment_info.currency} прошла успешно!\n"
            f"Теперь вы можете перейти к опроснику.",
            reply_markup=keyboard
        )
    else:
        # This case should ideally not be reached if the start handler works correctly
        await message.answer("Произошла ошибка. Пожалуйста, попробуйте начать сначала с /start.")

