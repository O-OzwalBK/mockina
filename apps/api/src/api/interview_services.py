"""The question source: the one place that turns a session's state into its next question.

Routes never talk to the engine or to skill extraction directly. They call an `Interviewer`.
Tests give the routes a scripted fake; the running API gives them `ModelInterviewer`, which does the real work:
1. Find the preparation's skill graph. The first time a preparation needs one, extract it from
   the job description with the model and save it. After that the saved graph is reused, so the
   model is asked about skills once per preparation, not once per question.
2. Ask the engine for the next question (or for the news that the interview is over).

Extraction is lazy on purpose.
Creating the first session locks the preparation's job text, so the graph is always built from the final text,
and a preparation that is never practised never costs a model call.
"""

import logging
from collections.abc import Sequence
from time import perf_counter
from typing import Protocol
from uuid import UUID

from contracts import (
    InterviewConfig,
    Preparation,
    Question,
    QuestionCountConfig,
    SkillGraph,
    Turn,
)
from engine import EngineOutcome, EngineSettings, InterviewFinished, next_turn
from llm_gateway import LLM
from session_store import SessionStore
from skill_graph import SkillCatalog, extract_skills

from api.locks import KeyedLocks
from api.model_calls import MeteredLLM

logger = logging.getLogger(__name__)


class Interviewer(Protocol):
    """Anything that can say what the next question of a session is."""

    async def next_question(
        self,
        *,
        user_id: UUID,
        preparation: Preparation,
        turns: Sequence[Turn],
        earlier_questions: Sequence[Question],
    ) -> EngineOutcome:
        """Return the next question, or `InterviewFinished` when the interview is over.

        `turns` are the questions already asked in this session. `earlier_questions` are the
        questions asked in the preparation's other sessions, so they are not repeated.
        """
        ...


def resolve_interview_config(settings: EngineSettings) -> InterviewConfig:
    """Choose how the interview ends: after the default number of questions.

    This is the single place that decides the end rule. Today it is the instance default.
    Later it will also read the user's, the preparation's and the session's own choices.
    """
    return QuestionCountConfig(count=settings.default_question_count)


class ModelInterviewer:
    """The real `Interviewer`: lazy skill extraction, then the engine, both using the model."""

    def __init__(
        self,
        llm: LLM,
        catalog: SkillCatalog,
        store: SessionStore,
        config: InterviewConfig,
    ) -> None:
        """Keep the model, the skill catalog, the store and the end rule for every question.

        The end rule is chosen once, when the server starts, and is not read again per
        question.
        """
        self._llm = llm
        self._catalog = catalog
        self._store = store
        self._config = config
        self._extraction_locks = KeyedLocks()

    async def next_question(
        self,
        *,
        user_id: UUID,
        preparation: Preparation,
        turns: Sequence[Turn],
        earlier_questions: Sequence[Question],
    ) -> EngineOutcome:
        """Ensure the skill graph exists, then ask the engine. Logs one line about the job."""
        meter = MeteredLLM(self._llm)
        started = perf_counter()
        outcome = "error"
        skills = "unknown"
        try:
            graph, extracted = await self._skill_graph(user_id, preparation, meter)
            skills = "extracted" if extracted else "saved"
            result = await next_turn(
                preparation, graph, turns, earlier_questions, self._config, meter
            )
            outcome = "finished" if isinstance(result, InterviewFinished) else "question"
            return result
        except BaseException as error:
            outcome = type(error).__name__
            raise
        finally:
            logger.info(
                "question outcome=%s skills=%s duration_ms=%d model_calls=%d "
                "prompt_tokens=%s completion_tokens=%s",
                outcome,
                skills,
                int((perf_counter() - started) * 1000),
                meter.calls,
                meter.prompt_tokens,
                meter.completion_tokens,
            )

    async def _skill_graph(
        self, user_id: UUID, preparation: Preparation, llm: LLM
    ) -> tuple[SkillGraph, bool]:
        """Return the preparation's skill graph, extracting and saving it if it has none yet.

        The second value says whether this call did the extraction. Only one request per
        preparation extracts at a time: the others wait on the lock, then find the saved graph.
        The graph is saved before the question is written, so if writing the question fails,
        the retry does not pay for the extraction again.
        """
        saved = await self._store.get_skill_graph(user_id, preparation.id)
        if saved is not None:
            return saved, False

        async with self._extraction_locks.hold(preparation.id):
            # Another request may have finished the extraction while this one waited.
            saved = await self._store.get_skill_graph(user_id, preparation.id)
            if saved is not None:
                return saved, False

            extracted = await extract_skills(
                llm,
                self._catalog,
                owner_id=str(user_id),
                job_title=preparation.job_title,
                job_description=preparation.job_description,
            )
            stored = await self._store.save_skill_graph_if_absent(
                user_id, preparation.id, extracted
            )
            return stored, True
