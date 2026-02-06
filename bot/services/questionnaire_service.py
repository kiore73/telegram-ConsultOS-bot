import logging
from collections import defaultdict
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database.models import Questionnaire, Question, QuestionLogic

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
    It should be initialized once on bot startup.
    """
    def __init__(self):
        self._caches: Dict[str, QuestionnaireCache] = {}

    async def load_from_db(self, session: AsyncSession):
        """
        Loads all questionnaires from the database and builds a cache for each.
        """
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
                cache.start_question_id = q_naire.questions[0].id
                for q in q_naire.questions:
                    options = q.options if q.options else []
                    cache.questions[q.id] = CachedQuestion(id=q.id, text=q.text, q_type=q.type, options=options)
                    for logic_rule in q.logic_rules:
                        cache.logic[q.id][logic_rule.answer_value] = logic_rule.next_question_id
            
            self._caches[q_naire.title] = cache
            logging.info(f"Loaded questionnaire '{q_naire.title}' with {len(cache.questions)} questions.")

    def get_questionnaire_by_title(self, title: str) -> Optional[QuestionnaireCache]:
        """Provides access to a specific questionnaire cache by its title."""
        return self._caches.get(title)

# --- Global instance ---
questionnaire_service = QuestionnaireService()