from aiogram import Router, F, types
from aiogram.types import Message, PreCheckoutQuery, SuccessfulPayment
from aiogram.fsm.context import FSMContext

from ..states.payment import PaymentFSM
from ..config import settings

router = Router()


@router.callback_query(F.data == "proceed_to_payment")
async def proceed_to_payment_handler(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Handles the 'Proceed to Payment' button press.
    Sends an invoice to the user.
    """
    await state.set_state(PaymentFSM.WAIT_PAYMENT)

    # TODO: Replace with actual product details and price
    PRICE = types.LabeledPrice(label="Консультация", amount=1000 * 100)  # Amount in kopecks (e.g., 1000 RUB)

    await callback_query.bot.send_invoice(
        chat_id=callback_query.from_user.id,
        title="Оплата услуги",
        description="Описание услуги для оплаты",
        payload="payment_payload",  # Internal bot payload
        provider_token=settings.YUKASSA_TOKEN.get_secret_value(),
        currency="RUB",
        prices=[PRICE],
        start_parameter="consultos-bot-payment",
        provider_data=None,  # Provider-specific data
    )
    await callback_query.answer()


@router.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: PreCheckoutQuery):
    """
    Handles pre-checkout queries. This is where you confirm you can fulfill the order.
    """
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message, state: FSMContext):
    """
    Handles successful payments.
    """
    await state.set_state(PaymentFSM.PAYMENT_SUCCESS)

    # Here you would update the user's status in the database, e.g., user.has_paid = True
    
    payment_info = message.successful_payment
    await message.answer(
        f"Оплата на сумму {payment_info.total_amount // 100} {payment_info.currency} прошла успешно!\n"
        f"Теперь вы можете перейти к опроснику."
        # TODO: Add a button to start the questionnaire
    )
