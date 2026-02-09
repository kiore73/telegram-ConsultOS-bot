import logging
from collections import defaultdict
from typing import Dict, List, Optional
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database.models import Questionnaire, Question, QuestionLogic
from ..states.questionnaire import QuestionnaireState


class CachedQuestion:
    """A lightweight, in-memory representation of a question."""
    def __init__(self, id: int, text: str, q_type: str, options: List[str]):
        self.id = id
        self.text = text
        self.type = q_type
        self.options = options

class QuestionnaireCache:
    """Holds a single questionnaire structure in memory for fast access."""
    def __init__(self):
        self.questions: Dict[int, CachedQuestion] = {}
        self.logic: Dict[int, Dict[str, Optional[int]]] = defaultdict(dict)
        self.start_question_id: Optional[int] = None

    def get_question(self, question_id: int) -> Optional[CachedQuestion]:
        return self.questions.get(question_id)

    def get_next_question_id(self, current_question_id: int, answer: str) -> Optional[int]:
        """Finds the next question ID based on the current question and answer."""
        question_logic = self.logic.get(current_question_id, {})
        if answer in question_logic:
            return question_logic[answer]
        return question_logic.get("любой")

class QuestionnaireService:
    """
    Manages loading and accessing multiple questionnaire caches from the database.
    """
    def __init__(self):
        self._caches: Dict[str, QuestionnaireCache] = {}

    async def load_from_db(self, session: AsyncSession):
        logging.info("Loading all questionnaires into memory cache...")
        
        stmt = select(Questionnaire).options(
            selectinload(Questionnaire.questions).selectinload(Question.logic_rules)
        )
        result = await session.execute(stmt)
        all_questionnaires = result.scalars().unique().all()

        if not all_questionnaires:
            logging.warning("No questionnaires found in the database.")
            return

        for q_naire in all_questionnaires:
            cache = QuestionnaireCache()
            if q_naire.questions:
                all_next_q_ids = {rule.next_question_id for q in q_naire.questions for rule in q.logic_rules}
                start_questions = [q.id for q in q_naire.questions if q.id not in all_next_q_ids]
                
                if start_questions:
                    cache.start_question_id = start_questions[0]
                else:
                    cache.start_question_id = q_naire.questions[0].id

                for q in q_naire.questions:
                    options = q.options if q.options else []
                    cache.questions[q.id] = CachedQuestion(id=q.id, text=q.text, q_type=q.type, options=options)
                    for logic_rule in q.logic_rules:
                        cache.logic[q.id][logic_rule.answer_value] = logic_rule.next_question_id
            
            self._caches[q_naire.title] = cache
            logging.info(f"Loaded questionnaire '{q_naire.title}' with {len(cache.questions)} questions.")

    def get_questionnaire_by_title(self, title: str) -> Optional[QuestionnaireCache]:
        return self._caches.get(title)

    async def start_questionnaire(self, bot: Bot, user_id: int, message_id: int, state: FSMContext, session: AsyncSession):
        from ..handlers import questionnaire as q_handler

        data = await state.get_data()
        pending = data.get("pending_questionnaires", [])
        
        if not pending:
            await bot.send_message(user_id, "Все опросы завершены!")
            await state.clear()
            return

        next_q_title = pending.pop(0)
        q_cache = self.get_questionnaire_by_title(next_q_title)

        if not q_cache or not q_cache.start_question_id:
            await bot.edit_message_text(chat_id=user_id, message_id=message_id, text=f"Не удалось запустить опросник '{next_q_title}'.")
            await q_handler.end_current_questionnaire_and_proceed(bot, user_id, message_id, state, session)
            return
        
        await state.set_state(QuestionnaireState.in_questionnaire)
        await state.update_data(
            pending_questionnaires=pending,
            current_questionnaire_title=next_q_title,
            question_history=[]
        )
        
        await q_handler.show_question(bot, user_id, message_id, state, session, q_cache.start_question_id)

questionnaire_service = QuestionnaireService()
