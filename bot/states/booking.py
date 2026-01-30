from aiogram.fsm.state import StatesGroup, State


class BookingFSM(StatesGroup):
    """
    Finite State Machine for the booking process.
    """
    DATE_SELECT = State()
    TIME_SELECT = State()
