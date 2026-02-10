from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.utils.markdown import hbold
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from bot_v2.database.models import User
from bot_v2.keyboards.start import get_tariffs_keyboard

router = Router()


@router.message(CommandStart())
async def command_start_handler(message: Message, session: AsyncSession) -> None:
    """
    This handler receives messages with `/start` command
    and registers the user if they don't exist.
    """
    result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        session.add(user)
        await session.commit()

    keyboard = await get_tariffs_keyboard(session)

    await message.answer(
        f"Привет, {hbold(message.from_user.full_name)}!\n\n"
        "Выберите подходящий тариф для консультации:",
        reply_markup=keyboard
    )
