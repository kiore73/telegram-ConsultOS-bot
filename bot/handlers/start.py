from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.utils.markdown import hbold

# Using a simple inline keyboard for now
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

router = Router()


@router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    This handler receives messages with `/start` command
    """
    # Create a simple inline keyboard
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Перейти к оплате", callback_data="proceed_to_payment")
            ]
        ]
    )

    await message.answer(
        f"Привет, {hbold(message.from_user.full_name)}!\n\n"
        "Здесь будет описание вашей услуги. Нажмите кнопку ниже, чтобы перейти к оплате.",
        reply_markup=keyboard
    )
