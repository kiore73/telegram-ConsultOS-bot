from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.utils.markdown import hbold
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database.models import User
from ..keyboards.start import get_tariffs_keyboard

router = Router()


@router.message(CommandStart())
async def command_start_handler(message: Message, session: AsyncSession) -> None:
    """
    This handler receives messages with `/start` command
    and registers the user if they don't exist.
    """
    # Check if user exists
    result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
    user = result.scalar_one_or_none()

    if user is None:
        # Create new user
        new_user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        session.add(new_user)
        await session.commit()

    keyboard = get_tariffs_keyboard()

    await message.answer(
        f"Привет, {hbold(message.from_user.full_name)}!\n\n"
        "Выберите подходящий тариф для консультации:",
        reply_markup=keyboard
    )
