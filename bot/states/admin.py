from aiogram.fsm.state import StatesGroup, State


class AdminFSM(StatesGroup):
    """
    Finite State Machine for admin panel actions.
    """
    MENU = State()  # Main admin menu
    ADD_SLOT_DATE = State()
    ADD_SLOT_TIME = State()
    ADD_SLOT_CONFIRM = State()
