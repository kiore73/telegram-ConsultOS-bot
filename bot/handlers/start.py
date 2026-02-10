import logging
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.utils.markdown import hbold
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..database.models import User
from ..keyboards.start import get_tariffs_keyboard

router = Router()


@router.message(CommandStart())
async def command_start_handler(message: Message, session: AsyncSession) -> None:
    """
    This handler receives messages with `/start` command
    and registers the user if they don't exist.
    """
    logging.info("command_start_handler: Received /start command.")
    result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
    user = result.scalar_one_or_none()

    if user is None:
        logging.info("command_start_handler: User not found, creating new user.")
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        session.add(user)
        await session.commit()
    else:
        logging.info("command_start_handler: User found.")

    keyboard = await get_tariffs_keyboard(session)

    await message.answer(
        f"Привет, {hbold(message.from_user.full_name)}!\n\n"
        "Выберите подходящий тариф для консультации:",
        reply_markup=keyboard
    )
    logging.info("command_start_handler: Sent welcome message.")
