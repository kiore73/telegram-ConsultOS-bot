from aiogram.fsm.state import StatesGroup, State


class QuestionnaireFSM(StatesGroup):
    """
    Finite State Machine for the questionnaire process.
    We use a single state and manage the flow using FSM data.
    """
    IN_QUESTIONNAIRE = State()
