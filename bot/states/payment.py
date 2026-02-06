from aiogram.fsm.state import StatesGroup, State


class PaymentFSM(StatesGroup):
    """
    Finite State Machine for the payment process.
    """
    CHOOSE_TARIFF = State()
    WAIT_PAYMENT = State()
    PAYMENT_SUCCESS = State()
    
    # States to hold data
    tariff_name = State()
    price = State()
