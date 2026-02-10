from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from bot_v2.states.payment import PaymentFSM
from bot_v2.states.tariff import TariffState
from bot_v2.database.models import User, Payment, Tariff
from bot.services.yookassa_service import YooKassaService
from bot_v2.keyboards.tariff import get_gender_keyboard

router = Router()

async def _initiate_payment(message: types.Message, state: FSMContext, session: AsyncSession, user: User, tariff: Tariff):
    """Common logic to start the payment process."""
    await state.set_state(PaymentFSM.WAIT_PAYMENT)
    
    yookassa_service = YooKassaService()
    description = f"Оплата тарифа '{tariff.name}'"
    metadata = {"user_id": user.telegram_id, "username": user.username, "tariff_id": tariff.id}

    payment_details = await yookassa_service.create_payment(
        amount=tariff.price,
        currency="RUB",
        description=description,
        metadata=metadata
    )

    if payment_details and "confirmation_url" in payment_details:
        payment_id = payment_details["id"]
        confirmation_url = payment_details["confirmation_url"]

        new_payment = Payment(
            user_id=user.id,
            amount=tariff.price,
            status="pending",
            provider_charge_id=payment_id
        )
        session.add(new_payment)
        
        user.tariff_id = tariff.id
        await session.commit()
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="➡️ Оплатить", url=confirmation_url)]
        ])
        
        await message.edit_text(
            f"Вы выбрали тариф '{tariff.name}'.\n"
            "Нажмите кнопку ниже, чтобы перейти к оплате. Подтверждение произойдет автоматически.",
            reply_markup=keyboard
        )
    else:
        await message.edit_text(
            "Не удалось создать ссылку на оплату. Попробуйте позже или свяжитесь с поддержкой."
        )

@router.callback_query(F.data.startswith("tariff:"))
async def select_tariff_handler(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    
    user_result = await session.execute(select(User).where(User.telegram_id == user_id))
    user = user_result.scalar_one()

    if user and user.has_paid and user.tariff_id:
        await callback.answer("Вы уже оплатили услугу.", show_alert=True)
        return

    tariff_name = callback.data.split(":")[1]
    
    tariff_result = await session.execute(select(Tariff).where(Tariff.name == tariff_name))
    tariff = tariff_result.scalar_one_or_none()

    if not tariff:
        await callback.answer("Тариф не найден.", show_alert=True)
        return

    if tariff.name == "Лайт":
        await state.set_state(TariffState.choosing_gender_for_lite)
        await state.update_data(tariff_id=tariff.id)
        await callback.message.edit_text(
            "Для тарифа 'Лайт' необходимо указать ваш пол, чтобы подобрать правильный опросник.",
            reply_markup=get_gender_keyboard()
        )
    else:
        await _initiate_payment(callback.message, state, session, user, tariff)
    
    await callback.answer()

@router.callback_query(TariffState.choosing_gender_for_lite, F.data.startswith("select_gender:"))
async def choose_gender_for_lite_handler(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    gender = callback.data.split(":")[1]
    user_data = await state.get_data()
    tariff_id = user_data.get('tariff_id')

    user_id = callback.from_user.id
    user_result = await session.execute(select(User).where(User.telegram_id == user_id))
    user = user_result.scalar_one()

    tariff_result = await session.execute(select(Tariff).where(Tariff.id == tariff_id))
    tariff = tariff_result.scalar_one()
    
    await state.update_data(gender=gender)
    
    await _initiate_payment(callback.message, state, session, user, tariff)
    await callback.answer()
