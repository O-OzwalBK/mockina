import json
from typing import Any

import pytest
from contracts import Answer, Question
from evaluator import EvaluationError, grade_answer
from llm_gateway import (
    Completion,
    ContextBudgetExceededError,
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMServerError,
    LLMTimeoutError,
)
from llm_gateway.testing import FakeLLM

QUESTION_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"


@pytest.fixture
def anyio_backend():
    """Run asynchronous grading tests on asyncio only."""
    return "asyncio"


def _question() -> Question:
    """The question every test grades."""
    return Question(
        id=QUESTION_ID,
        text="How does React decide when to re-render a component?",
        skill_id="react-rendering",
        difficulty=3,
    )


def _answer(transcript: str = "React re-renders when state or props change.") -> Answer:
    """A spoken answer with the given transcript."""
    return Answer(transcript=transcript, duration=20.0)


def valid_reply() -> dict[str, Any]:
    """A complete, valid grading reply."""
    data: dict[str, Any] = {"summary": "Solid answer overall."}
    for metric, score in {
        "correctness": 7,
        "depth": 6,
        "clarity": 8,
        "relevance": 7,
    }.items():
        data[metric] = {"score": score, "feedback": "Reasonable."}
    return data


def _completion(data: object, *, finish_reason: str | None = "stop") -> Completion:
    """Serialize a value as a model reply with a configurable finish reason."""
    return Completion(text=json.dumps(data), model="fake-model", finish_reason=finish_reason)


async def _grade(llm: FakeLLM, *, answer: Answer | None = None):
    """Call the evaluator with the standard question and answer."""
    return await grade_answer(
        llm,
        question=_question(),
        answer=answer or _answer(),
        job_title="Frontend Engineer",
    )


@pytest.mark.anyio
async def test_a_valid_reply_becomes_an_evaluation_with_the_questions_id():
    """A good first reply needs no repair and carries the server's question id."""
    llm = FakeLLM(_completion(valid_reply()))
    evaluation = await _grade(llm)
    assert evaluation.question_id == _question().id
    assert evaluation.correctness.score == 7
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_grading_uses_temperature_zero():
    """Grading is deterministic, so the model gets temperature 0."""
    llm = FakeLLM(_completion(valid_reply()))
    await _grade(llm)
    assert llm.calls[0].temperature == 0.0


@pytest.mark.anyio
async def test_silence_returns_a_fixed_evaluation_without_a_model_call():
    """An empty transcript never reaches the model and gets a clear zero-score grade."""
    llm = FakeLLM()
    evaluation = await _grade(llm, answer=_answer("  \n\t  "))
    assert llm.calls == []
    assert evaluation.correctness.score == 0
    assert evaluation.depth.score == 0
    assert evaluation.clarity.score == 0
    assert evaluation.relevance.score == 0
    assert evaluation.summary.startswith("The answer was empty.")


@pytest.mark.anyio
async def test_unparseable_json_gets_one_correction_and_then_succeeds():
    """A bad first reply is repaired once with the previous reply fenced."""
    llm = FakeLLM("not JSON", _completion(valid_reply()))
    evaluation = await _grade(llm)
    assert evaluation.correctness.score == 7
    assert len(llm.calls) == 2
    correction = llm.calls[1].messages[-1].content
    assert "Previous model reply" in correction
    assert "```text\nnot JSON\n```" in correction
    assert "invalid_json" in correction


@pytest.mark.anyio
async def test_an_invalid_score_is_named_in_the_correction():
    """The repair tells the model which check failed, not just 'try again'."""
    bad = valid_reply()
    bad["correctness"]["score"] = 11
    llm = FakeLLM(_completion(bad), _completion(valid_reply()))
    evaluation = await _grade(llm)
    assert evaluation.correctness.score == 7
    assert "invalid_score" in llm.calls[1].messages[-1].content


@pytest.mark.anyio
async def test_two_bad_replies_raise_evaluation_error():
    """After one failed repair the evaluator reports a safe, non-retryable error."""
    llm = FakeLLM("not JSON", "still not JSON")
    with pytest.raises(EvaluationError) as caught:
        await _grade(llm)
    error = caught.value
    assert error.attempts == 2
    assert error.failures == ("invalid_json",)
    assert error.retryable is False
    assert len(llm.calls) == 2


@pytest.mark.anyio
async def test_the_evaluation_error_does_not_echo_the_answer_or_reply():
    """The error names checks only; it never repeats the transcript or the model text."""
    marker = "private-answer-marker"
    llm = FakeLLM(f"reply-{marker}", f"reply-{marker}")
    with pytest.raises(EvaluationError) as caught:
        await _grade(llm, answer=_answer(marker))
    assert marker not in str(caught.value)


@pytest.mark.anyio
async def test_a_truncated_first_reply_is_not_repaired():
    """A length-stopped reply points at the output setting and makes no second call."""
    llm = FakeLLM(_completion(valid_reply(), finish_reason="length"))
    with pytest.raises(LLMResponseError, match="LLM_MAX_OUTPUT_TOKENS"):
        await _grade(llm)
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_a_truncated_repair_is_not_tried_again():
    """Truncation after a bad first reply still fails immediately, with two calls total."""
    llm = FakeLLM("not JSON", _completion(valid_reply(), finish_reason="length"))
    with pytest.raises(LLMResponseError):
        await _grade(llm)
    assert len(llm.calls) == 2


@pytest.mark.anyio
async def test_a_huge_previous_reply_is_bounded_in_the_correction():
    """The repair prompt does not grow without limit when the first reply is huge."""
    huge = "not JSON " + "x" * 20_000
    llm = FakeLLM(huge, _completion(valid_reply()))
    await _grade(llm)
    assert len(llm.calls[1].messages[-1].content) < 10_000


@pytest.mark.anyio
async def test_a_model_supplied_question_id_is_ignored():
    """The evaluator always uses the Question's id, never the model's."""
    data = valid_reply()
    data["question_id"] = "00000000-0000-0000-0000-000000000000"
    llm = FakeLLM(_completion(data))
    evaluation = await _grade(llm)
    assert evaluation.question_id == _question().id


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [
        ContextBudgetExceededError("too long"),
        LLMAuthError("bad key"),
        LLMConnectionError("offline"),
        LLMRateLimitError("busy"),
        LLMRequestError("bad request"),
        LLMResponseError("bad response"),
        LLMServerError("server issue"),
        LLMTimeoutError("slow"),
    ],
    ids=lambda error: type(error).__name__,
)
async def test_gateway_errors_pass_through_without_repair(error):
    """Every gateway failure keeps its type and is not wrapped or repaired."""
    llm = FakeLLM(error, _completion(valid_reply()))
    with pytest.raises(type(error)) as caught:
        await _grade(llm)
    assert caught.value is error


@pytest.mark.anyio
async def test_a_budget_error_on_the_repair_passes_through():
    """If the repair prompt no longer fits, the gateway error is not turned into EvaluationError."""
    llm = FakeLLM("not JSON", ContextBudgetExceededError("too long"))
    with pytest.raises(ContextBudgetExceededError):
        await _grade(llm)
    assert len(llm.calls) == 2
