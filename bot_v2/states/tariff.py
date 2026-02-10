from aiogram.fsm.state import StatesGroup, State


class TariffState(StatesGroup):
    choosing_gender_for_lite = State()
