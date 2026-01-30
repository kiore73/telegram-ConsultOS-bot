from aiogram.fsm.state import StatesGroup, State


class PaymentFSM(StatesGroup):
    """
    Finite State Machine for the payment process.
    """
    SERVICE_INFO = State()
    WAIT_PAYMENT = State()
    PAYMENT_SUCCESS = State()
