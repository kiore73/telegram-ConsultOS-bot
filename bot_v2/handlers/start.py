from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

# For now, we won't interact with the User model to keep it simple.
# We will just prove the handler is reached.

router = Router()

@router.message(CommandStart())
async def command_start_handler(message: Message, session: AsyncSession) -> None:
    """
    This handler receives messages with `/start` command.
    """
    # Proof that the handler and db session are working
    await message.answer("Bot v2 is running! Database session is available.")
