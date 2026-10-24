import random

import pytest
from contracts import (
    Answer,
    AnswerTimeConfig,
    ModelDecidesConfig,
    Preparation,
    Question,
    QuestionCountConfig,
    SkillGraph,
    SkillNode,
    Turn,
    TurnStatus,
    skill_id,
)
from engine import FinishedReason, InterviewFinished, UnusableQuestionError, next_turn
from llm_gateway import (
    ContextBudgetExceededError,
    LLMAuthError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMServerError,
    LLMTimeoutError,
)
from llm_gateway.testing import FakeLLM

ROOT = "React"


@pytest.fixture
def anyio_backend():
    """Run asynchronous flow tests on asyncio only."""
    return "asyncio"


def _graph(*, importances=(3, 3, 3), difficulties=(3, 3, 3)) -> SkillGraph:
    """A React root with three leaves: Hooks, State, and Effects."""
    root = SkillNode(
        id=skill_id(ROOT, ROOT),
        label=ROOT,
        parent_id=None,
        importance=None,
        difficulty=None,
    )
    leaves = [
        SkillNode(
            id=skill_id(ROOT, label),
            label=label,
            parent_id=root.id,
            importance=importance,
            difficulty=difficulty,
        )
        for label, importance, difficulty in zip(
            ("Hooks", "State", "Effects"), importances, difficulties, strict=True
        )
    ]
    return SkillGraph(nodes=(root, *leaves))


def _preparation() -> Preparation:
    """A small preparation for the engine to ask about."""
    return Preparation(
        job_title="Frontend Engineer",
        job_description="Build user interfaces with React and TypeScript.",
        resume="Built a task tracker with React.",
    )


def _answered_turn(skill: str, duration: float = 10.0) -> Turn:
    """One answered turn for the given skill."""
    question = Question(text=f"Explain {skill}.", skill_id=skill, difficulty=2)
    answer = Answer(transcript="An answer.", duration=duration)
    return Turn(question=question, status=TurnStatus.AWAITING_GRADE, answer=answer)


def _turn(skill: str, difficulty: int = 2) -> Turn:
    """One unanswered turn for the given skill."""
    return Turn(question=Question(text=f"Explain {skill}.", skill_id=skill, difficulty=difficulty))


def _leaf(label: str) -> str:
    """The stable id of a leaf under the React root."""
    return skill_id(ROOT, label)


async def _next(config, llm, *, turns=(), earlier=(), graph=None, seed=0):
    """Call the engine with the standard preparation and a deterministic random source."""
    return await next_turn(
        _preparation(),
        graph or _graph(),
        list(turns),
        list(earlier),
        config,
        llm,
        random_source=random.Random(seed),
    )


@pytest.mark.anyio
async def test_next_turn_returns_a_question_when_the_interview_continues():
    """A running interview opens the next turn with a question for a real skill."""
    llm = FakeLLM("How does React batch state updates?")
    outcome = await _next(QuestionCountConfig(count=1), llm)
    assert isinstance(outcome, Question)
    assert outcome.text == "How does React batch state updates?"
    assert outcome.skill_id in {_leaf("Hooks"), _leaf("State"), _leaf("Effects")}


@pytest.mark.anyio
async def test_question_count_reached_returns_finished_without_calling_the_model():
    """Reaching the question count ends the interview before any model call."""
    llm = FakeLLM()
    outcome = await _next(QuestionCountConfig(count=1), llm, turns=[_turn(_leaf("Hooks"))])
    assert outcome == InterviewFinished(reason=FinishedReason.QUESTION_COUNT_REACHED)
    assert llm.calls == []


@pytest.mark.anyio
async def test_answer_time_reached_returns_finished_without_calling_the_model():
    """Using up the answering time ends the interview before any model call."""
    llm = FakeLLM()
    config = AnswerTimeConfig(max_seconds=60)
    outcome = await _next(config, llm, turns=[_answered_turn(_leaf("Hooks"), duration=60.0)])
    assert outcome == InterviewFinished(reason=FinishedReason.ANSWER_TIME_REACHED)
    assert llm.calls == []


@pytest.mark.anyio
async def test_model_decides_below_the_minimum_writes_without_a_decision_call():
    """Below the minimum the engine asks directly, so only the question call is made."""
    llm = FakeLLM("How does React batch state updates?")
    config = ModelDecidesConfig(min_questions=3, max_questions=12)
    outcome = await _next(config, llm)
    assert isinstance(outcome, Question)
    assert len(llm.calls) == 1
    assert "continue or finish" not in llm.calls[0].messages[0].content


@pytest.mark.anyio
async def test_model_decides_at_the_maximum_finishes_without_a_decision_call():
    """At the maximum code ends the interview and asks the model nothing."""
    llm = FakeLLM()
    config = ModelDecidesConfig(min_questions=3, max_questions=12)
    turns = [_turn(_leaf("Hooks")) for _ in range(12)]
    outcome = await _next(config, llm, turns=turns)
    assert outcome == InterviewFinished(reason=FinishedReason.QUESTION_COUNT_REACHED)
    assert llm.calls == []


@pytest.mark.anyio
async def test_model_decides_inside_the_range_makes_the_decision_call_then_writes():
    """Inside the open range the decision call comes first and a continue leads to a question."""
    llm = FakeLLM("continue", "How does React batch state updates?")
    config = ModelDecidesConfig(min_questions=3, max_questions=12)
    turns = [_turn(_leaf("Hooks")) for _ in range(5)]
    outcome = await _next(config, llm, turns=turns)
    assert isinstance(outcome, Question)
    assert len(llm.calls) == 2
    assert "continue or finish" in llm.calls[0].messages[0].content


@pytest.mark.anyio
async def test_model_decides_finish_is_honoured_without_writing_a_question():
    """A finish decision ends the interview with the model reason and no question call."""
    llm = FakeLLM("finish")
    config = ModelDecidesConfig(min_questions=3, max_questions=12)
    turns = [_turn(_leaf("Hooks")) for _ in range(5)]
    outcome = await _next(config, llm, turns=turns)
    assert outcome == InterviewFinished(reason=FinishedReason.MODEL_DECIDED)
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_the_flow_uses_the_selected_skill_and_its_difficulty():
    """The question carries the chosen skill and the first-ask difficulty from the graph."""
    llm = FakeLLM("How does React batch state updates?")
    graph = _graph(importances=(1, 5, 1), difficulties=(5, 5, 5))
    outcome = await _next(QuestionCountConfig(count=1), llm, graph=graph)
    assert isinstance(outcome, Question)
    assert outcome.skill_id == _leaf("State")
    assert outcome.difficulty == 4


@pytest.mark.anyio
async def test_earlier_questions_reach_the_prompt():
    """The model sees the earlier questions for the chosen skill, so it can avoid them."""
    llm = FakeLLM("How does React batch state updates?")
    earlier = [
        Question(text="What is a hook?", skill_id=_leaf("Hooks"), difficulty=2),
        Question(text="What is a closure?", skill_id=_leaf("State"), difficulty=2),
        Question(text="What is an effect?", skill_id=_leaf("Effects"), difficulty=2),
    ]
    await _next(
        QuestionCountConfig(count=1),
        llm,
        earlier=earlier,
        graph=_graph(importances=(1, 5, 1)),
    )
    assert "What is a closure?" in llm.calls[0].messages[1].content


@pytest.mark.anyio
async def test_a_bad_question_is_repaired_once_and_returned():
    """The flow returns the second, usable question after one repair."""
    bad = "x" * 301
    llm = FakeLLM(bad, "How does React batch state updates?")
    outcome = await _next(QuestionCountConfig(count=1), llm)
    assert isinstance(outcome, Question)
    assert outcome.text == "How does React batch state updates?"
    assert len(llm.calls) == 2


@pytest.mark.anyio
async def test_two_bad_questions_raise_the_package_error():
    """After one failed repair the flow raises UnusableQuestionError, not a finish or a turn."""
    llm = FakeLLM("What is `code`?", "y" * 301)
    with pytest.raises(UnusableQuestionError):
        await _next(QuestionCountConfig(count=1), llm)


GATEWAY_ERRORS = [
    LLMConnectionError("unreachable"),
    LLMTimeoutError("timed out"),
    LLMRateLimitError("busy", retry_after=1.0),
    LLMServerError("server error"),
    LLMAuthError("bad key"),
    LLMRequestError("rejected request"),
    LLMResponseError("bad response"),
    ContextBudgetExceededError("too long", estimated_tokens=20, budget_tokens=10),
]


@pytest.mark.anyio
@pytest.mark.parametrize("error", GATEWAY_ERRORS, ids=lambda error: type(error).__name__)
async def test_gateway_errors_pass_through_unmodified(error):
    """The engine never catches, wraps, or replaces a gateway error."""
    llm = FakeLLM(error)
    with pytest.raises(LLMError) as raised:
        await _next(QuestionCountConfig(count=1), llm)
    assert raised.value is error
