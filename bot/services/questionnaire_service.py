import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database.models import Question, QuestionLogic

# --- Data Structures for Cached Questionnaire ---

class CachedQuestion:
    """A lightweight, in-memory representation of a question."""
    def __init__(self, id: int, text: str, q_type: str, options: List[str]):
        self.id = id
        self.text = text
        self.type = q_type
        self.options = options

class QuestionnaireCache:
    """Holds the entire questionnaire structure in memory for fast access."""
    def __init__(self):
        # {question_id: CachedQuestion}
        self.questions: Dict[int, CachedQuestion] = {}
        # {question_id: {answer_value: next_question_id}}
        self.logic: Dict[int, Dict[str, Optional[int]]] = defaultdict(dict)
        self.start_question_id: Optional[int] = None

    def get_question(self, question_id: int) -> Optional[CachedQuestion]:
        return self.questions.get(question_id)

    def get_next_question_id(self, current_question_id: int, answer: str) -> Optional[int]:
        """Finds the next question ID based on the current question and answer."""
        question_logic = self.logic.get(current_question_id, {})
        # Exact match first
        if answer in question_logic:
            return question_logic[answer]
        # Fallback to a generic "any" rule
        if "любой" in question_logic:
            return question_logic["любой"]
        return None

# --- Service to Build and Hold the Cache ---

class QuestionnaireService:
    """
    This service is responsible for loading the questionnaire from the database
    into an in-memory cache for ultra-fast access during a user's session.
    It should be initialized once on bot startup.
    """
    def __init__(self):
        self._cache = QuestionnaireCache()

    async def load_from_db(self, session: AsyncSession):
        """
        Loads all questions and their logic from the database and builds the cache.
        This should be called once on startup.
        """
        logging.info("Loading questionnaire into memory cache...")
        
        # Eagerly load questions with their logic rules
        stmt = select(Question).options(selectinload(Question.logic_rules)).order_by(Question.id)
        result = await session.execute(stmt)
        all_questions = result.scalars().all()

        if not all_questions:
            logging.warning("No questions found in the database. Questionnaire will be empty.")
            return

        # Ensure start_question_id is set only if questions exist
        self._cache.start_question_id = all_questions[0].id if all_questions else None

        for q in all_questions:
            # Reconstruct options for CachedQuestion from logic_rules if needed
            # For this new robust service, let's collect actual options from logic_rules
            options = [logic.answer_value for logic in q.logic_rules if logic.answer_value != "любой"]
            self._cache.questions[q.id] = CachedQuestion(
                id=q.id, text=q.text, q_type=q.type, options=options
            )
            for logic_rule in q.logic_rules:
                self._cache.logic[q.id][logic_rule.answer_value] = logic_rule.next_question_id
        
        logging.info(f"Successfully loaded {len(self._cache.questions)} questions into cache. Starting with QID {self._cache.start_question_id}.")

    def get_cache(self) -> QuestionnaireCache:
        """Provides access to the loaded questionnaire cache."""
        return self._cache

# --- Global instance ---
# This will be created once and used throughout the application
questionnaire_service = QuestionnaireService()