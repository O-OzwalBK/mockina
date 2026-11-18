"""Tests for the model-backed question source (lazy skill extraction, then the engine)."""

import asyncio
import json
import logging
from collections.abc import Sequence
from uuid import UUID

import pytest
from api.interview_services import ModelInterviewer, resolve_interview_config
from contracts import Answer, Preparation, PreparationCreate, Question, QuestionCountConfig
from engine import EngineSettings, FinishedReason, InterviewFinished
from llm_gateway import LLM, ChatMessage, Completion, LLMTimeoutError
from llm_gateway.testing import FakeLLM
from session_store import InMemorySessionStore
from skill_graph import InMemorySkillStore, SkillExtractionError, SkillGraphError

JOB_MARKER = "job-text-marker-7f3a"
RESUME_MARKER = "resume-text-marker-91bc"

FIRST_QUESTION = "How would you decide between useState and useReducer in a React component?"
SECOND_QUESTION = "What problem does the dependency array of useEffect solve for you?"


@pytest.fixture
def anyio_backend():
    """Run these asynchronous tests on asyncio only."""
    return "asyncio"


class SlowLLM:
    """Wrap a model so every call pauses first, letting other requests run in the meantime."""

    def __init__(self, llm: FakeLLM) -> None:
        """Wrap the scripted model."""
        self._llm = llm

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ) -> Completion:
        """Pause briefly, then forward the call."""
        await asyncio.sleep(0.02)
        return await self._llm.complete(
            messages, temperature=temperature, max_output_tokens=max_output_tokens
        )


def extraction_reply() -> str:
    """A valid skill-extraction reply: one React category with three skills."""
    return json.dumps(
        {
            "categories": [
                {
                    "label": "React",
                    "skills": [
                        {"label": "hooks", "importance": 4, "difficulty": 2},
                        {"label": "routing", "importance": 3, "difficulty": 3},
                        {"label": "state", "importance": 5, "difficulty": 3},
                    ],
                }
            ]
        }
    )


async def make_preparation(store: InMemorySessionStore) -> tuple[Preparation, UUID]:
    """Create a user and a preparation whose texts carry privacy markers."""
    user = await store.create_user("hash-" + str(id(store)))
    preparation = await store.create_preparation(
        user.id,
        PreparationCreate(
            job_title="Junior React Developer",
            job_description=f"Build interfaces with React. {JOB_MARKER}",
            resume=f"Built a task tracker. {RESUME_MARKER}",
        ),
    )
    return preparation, user.id


def build_interviewer(
    llm: LLM,
    store: InMemorySessionStore,
    skill_store: InMemorySkillStore,
    count: int = 5,
) -> ModelInterviewer:
    """A real interviewer reading and writing the given doubles."""
    return ModelInterviewer(llm, skill_store.catalog, store, QuestionCountConfig(count=count))


def test_the_interview_config_is_the_engines_default_question_count():
    """Until layered configuration exists, every interview ends after the default count."""
    settings = EngineSettings(_env_file=None, default_question_count=3)  # pyright: ignore[reportCallIssue]

    assert resolve_interview_config(settings) == QuestionCountConfig(count=3)


@pytest.mark.anyio
async def test_the_first_question_extracts_the_skills_and_saves_them(
    store: InMemorySessionStore, skill_store: InMemorySkillStore
):
    """With no saved graph, the interviewer extracts one, stores it, then asks a question."""
    preparation, user_id = await make_preparation(store)
    llm = FakeLLM(extraction_reply(), FIRST_QUESTION)
    interviewer = build_interviewer(llm, store, skill_store)

    outcome = await interviewer.next_question(
        user_id=user_id, preparation=preparation, turns=(), earlier_questions=()
    )

    assert isinstance(outcome, Question)
    assert outcome.text == FIRST_QUESTION
    saved = await store.get_skill_graph(user_id, preparation.id)
    assert saved is not None
    assert outcome.skill_id in {node.id for node in saved.nodes}
    assert len(llm.calls) == 2


@pytest.mark.anyio
async def test_a_saved_graph_is_reused_without_extracting_again(
    store: InMemorySessionStore, skill_store: InMemorySkillStore
):
    """The second question of a preparation costs one model call, not two."""
    preparation, user_id = await make_preparation(store)
    llm = FakeLLM(extraction_reply(), FIRST_QUESTION, SECOND_QUESTION)
    interviewer = build_interviewer(llm, store, skill_store)

    await interviewer.next_question(
        user_id=user_id, preparation=preparation, turns=(), earlier_questions=()
    )
    await interviewer.next_question(
        user_id=user_id, preparation=preparation, turns=(), earlier_questions=()
    )

    assert len(llm.calls) == 3


@pytest.mark.anyio
async def test_two_simultaneous_first_questions_extract_the_skills_only_once(
    store: InMemorySessionStore, skill_store: InMemorySkillStore
):
    """Two requests racing on a new preparation share one extraction (one lock per preparation)."""
    preparation, user_id = await make_preparation(store)
    llm = FakeLLM(extraction_reply(), FIRST_QUESTION, SECOND_QUESTION)
    interviewer = build_interviewer(SlowLLM(llm), store, skill_store)

    outcomes = await asyncio.gather(
        interviewer.next_question(
            user_id=user_id, preparation=preparation, turns=(), earlier_questions=()
        ),
        interviewer.next_question(
            user_id=user_id, preparation=preparation, turns=(), earlier_questions=()
        ),
    )

    assert all(isinstance(outcome, Question) for outcome in outcomes)
    assert len(llm.calls) == 3
    assert await store.get_skill_graph(user_id, preparation.id) is not None


@pytest.mark.anyio
async def test_a_failed_extraction_saves_nothing_and_the_next_attempt_extracts_again(
    store: InMemorySessionStore, skill_store: InMemorySkillStore
):
    """When the model cannot produce a graph, no half-result is stored, so a retry starts clean."""
    preparation, user_id = await make_preparation(store)
    llm = FakeLLM("not json", "still not json", extraction_reply(), FIRST_QUESTION)
    interviewer = build_interviewer(llm, store, skill_store)

    with pytest.raises(SkillGraphError):
        await interviewer.next_question(
            user_id=user_id, preparation=preparation, turns=(), earlier_questions=()
        )
    assert await store.get_skill_graph(user_id, preparation.id) is None

    outcome = await interviewer.next_question(
        user_id=user_id, preparation=preparation, turns=(), earlier_questions=()
    )

    assert isinstance(outcome, Question)


@pytest.mark.anyio
async def test_the_graph_is_saved_before_the_question_is_written(
    store: InMemorySessionStore, skill_store: InMemorySkillStore
):
    """If the question call fails, the extraction is kept, so the retry does not pay for it twice."""
    preparation, user_id = await make_preparation(store)
    llm = FakeLLM(extraction_reply(), LLMTimeoutError("The model did not answer."), FIRST_QUESTION)
    interviewer = build_interviewer(llm, store, skill_store)

    with pytest.raises(LLMTimeoutError):
        await interviewer.next_question(
            user_id=user_id, preparation=preparation, turns=(), earlier_questions=()
        )

    assert await store.get_skill_graph(user_id, preparation.id) is not None


@pytest.mark.anyio
async def test_one_log_line_per_question_reports_the_outcome_and_never_the_job_text(
    store: InMemorySessionStore,
    skill_store: InMemorySkillStore,
    caplog: pytest.LogCaptureFixture,
):
    """The log says what happened and how long it took, but holds no job, resume or question text."""
    preparation, user_id = await make_preparation(store)
    interviewer = build_interviewer(FakeLLM(extraction_reply(), FIRST_QUESTION), store, skill_store)
    caplog.set_level(logging.DEBUG)

    await interviewer.next_question(
        user_id=user_id, preparation=preparation, turns=(), earlier_questions=()
    )

    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("question ")]
    assert len(lines) == 1
    assert "outcome=question" in lines[0]
    assert "skills=extracted" in lines[0]
    assert "model_calls=2" in lines[0]
    assert "duration_ms=" in lines[0]
    for secret in (JOB_MARKER, RESUME_MARKER, FIRST_QUESTION, "Junior React Developer"):
        assert secret not in caplog.text


@pytest.mark.anyio
async def test_a_failed_question_is_logged_by_its_error_type_only(
    store: InMemorySessionStore,
    skill_store: InMemorySkillStore,
    caplog: pytest.LogCaptureFixture,
):
    """A failure is logged as the class name of the error, never its message."""
    preparation, user_id = await make_preparation(store)
    interviewer = build_interviewer(FakeLLM("not json", "still not json"), store, skill_store)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(SkillExtractionError):
        await interviewer.next_question(
            user_id=user_id, preparation=preparation, turns=(), earlier_questions=()
        )

    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("question ")]
    assert len(lines) == 1
    assert "outcome=SkillExtractionError" in lines[0]
    assert JOB_MARKER not in caplog.text


@pytest.mark.anyio
async def test_a_finished_interview_is_reported_without_asking_the_model_again(
    store: InMemorySessionStore,
    skill_store: InMemorySkillStore,
    caplog: pytest.LogCaptureFixture,
):
    """Once the end rule is reached the answer is `InterviewFinished`, with no new model call."""
    preparation, user_id = await make_preparation(store)
    llm = FakeLLM(extraction_reply(), FIRST_QUESTION)
    interviewer = build_interviewer(llm, store, skill_store, count=1)
    first = await interviewer.next_question(
        user_id=user_id, preparation=preparation, turns=(), earlier_questions=()
    )
    assert isinstance(first, Question)
    session = await store.create_session(user_id, preparation.id)
    turn = await store.add_question(user_id, session.id, first)
    await store.record_answer(
        user_id, session.id, turn.question.id, Answer(transcript="An answer.", duration=5.0)
    )
    stored = await store.get_session(user_id, session.id)
    assert stored is not None
    calls_before = len(llm.calls)
    caplog.set_level(logging.DEBUG)

    outcome = await interviewer.next_question(
        user_id=user_id, preparation=preparation, turns=stored.turns, earlier_questions=()
    )

    assert isinstance(outcome, InterviewFinished)
    assert outcome.reason == FinishedReason.QUESTION_COUNT_REACHED
    assert len(llm.calls) == calls_before
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("question ")]
    assert len(lines) == 1
    assert "outcome=finished" in lines[0]
    assert "skills=saved" in lines[0]
    assert "model_calls=0" in lines[0]
