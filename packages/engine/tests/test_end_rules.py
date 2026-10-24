import pytest
from contracts import (
    Answer,
    AnswerTimeConfig,
    ModelDecidesConfig,
    Question,
    QuestionCountConfig,
    Turn,
    TurnStatus,
)
from engine import FinishedReason, InterviewFinished
from engine.end_rules import is_finished
from llm_gateway import LLMResponseError
from llm_gateway.testing import FakeLLM


@pytest.fixture
def anyio_backend():
    """Run asynchronous end-rule tests on asyncio only."""
    return "asyncio"


def _turn(number: int, duration: float = 10.0) -> Turn:
    """One answered turn, used to reach a question count or a total answering time."""
    question = Question(text=f"Question {number}?", skill_id="skill", difficulty=2)
    answer = Answer(transcript="An answer.", duration=duration)
    return Turn(question=question, status=TurnStatus.AWAITING_GRADE, answer=answer)


def _turns(count: int, duration: float = 10.0) -> list[Turn]:
    """A session with the given number of answered turns."""
    return [_turn(number, duration) for number in range(count)]


@pytest.mark.anyio
@pytest.mark.parametrize("questions_asked", [0, 1, 2])
async def test_question_count_keeps_running_below_the_limit(questions_asked):
    """Below the configured count the interview is not finished and the model is not asked."""
    llm = FakeLLM()
    result = await is_finished(QuestionCountConfig(count=3), _turns(questions_asked), llm)
    assert result is None
    assert llm.calls == []


@pytest.mark.anyio
async def test_question_count_finishes_at_the_limit():
    """Reaching the configured count finishes the interview with the count reason."""
    llm = FakeLLM()
    result = await is_finished(QuestionCountConfig(count=3), _turns(3), llm)
    assert result == InterviewFinished(reason=FinishedReason.QUESTION_COUNT_REACHED)
    assert llm.calls == []


@pytest.mark.anyio
@pytest.mark.parametrize("total_duration,expected", [(110.0, None), (120.0, True), (130.0, True)])
async def test_answer_time_finishes_at_or_above_the_cap(total_duration, expected):
    """Total answered time below the cap keeps running; at or above it finishes."""
    llm = FakeLLM()
    turns = [_turn(1, duration=total_duration / 2), _turn(2, duration=total_duration / 2)]
    result = await is_finished(AnswerTimeConfig(max_seconds=120), turns, llm)
    if expected is None:
        assert result is None
    else:
        assert result == InterviewFinished(reason=FinishedReason.ANSWER_TIME_REACHED)
    assert llm.calls == []


@pytest.mark.anyio
async def test_unanswered_turns_do_not_count_towards_answer_time():
    """Only answered turns add answering time, so an open turn cannot end the interview."""
    llm = FakeLLM()
    open_turn = Turn(question=Question(text="Open?", skill_id="skill", difficulty=2))
    result = await is_finished(AnswerTimeConfig(max_seconds=60), [_turn(1, 30.0), open_turn], llm)
    assert result is None


@pytest.mark.anyio
@pytest.mark.parametrize("questions_asked", [0, 1, 2])
async def test_model_decides_does_not_call_the_model_below_the_minimum(questions_asked):
    """Before the minimum the engine asks directly, saving a decision call."""
    llm = FakeLLM()
    config = ModelDecidesConfig(min_questions=3, max_questions=12)
    result = await is_finished(config, _turns(questions_asked), llm)
    assert result is None
    assert llm.calls == []


@pytest.mark.anyio
async def test_model_decides_honours_a_finish_reply():
    """Inside the range a finish reply ends the interview with the model reason."""
    llm = FakeLLM("finish")
    config = ModelDecidesConfig(min_questions=3, max_questions=12)
    result = await is_finished(config, _turns(5), llm)
    assert result == InterviewFinished(reason=FinishedReason.MODEL_DECIDED)
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_model_decides_honours_a_continue_reply():
    """Inside the range a continue reply leaves the interview running."""
    llm = FakeLLM("continue")
    config = ModelDecidesConfig(min_questions=3, max_questions=12)
    result = await is_finished(config, _turns(5), llm)
    assert result is None
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_model_decides_forces_a_finish_at_the_maximum_without_a_call():
    """At the maximum code ends the interview and never asks the model."""
    llm = FakeLLM()
    config = ModelDecidesConfig(min_questions=3, max_questions=12)
    result = await is_finished(config, _turns(12), llm)
    assert result == InterviewFinished(reason=FinishedReason.QUESTION_COUNT_REACHED)
    assert llm.calls == []


@pytest.mark.anyio
async def test_decision_prompt_includes_the_position_and_the_range():
    """The decision prompt states questions asked, minimum, and maximum, so the model does not drift."""
    llm = FakeLLM("continue")
    config = ModelDecidesConfig(min_questions=3, max_questions=12)
    await is_finished(config, _turns(5), llm)
    prompt = "\n".join(message.content for message in llm.calls[0].messages)
    assert "5" in prompt
    assert "3" in prompt
    assert "12" in prompt


@pytest.mark.anyio
@pytest.mark.parametrize("reply", [" FINISH\n", "Finish", "finish"])
async def test_finish_reply_is_read_case_insensitively_after_trimming(reply):
    """The two allowed words are read after trimming and folding case."""
    llm = FakeLLM(reply)
    config = ModelDecidesConfig(min_questions=3, max_questions=12)
    result = await is_finished(config, _turns(5), llm)
    assert result == InterviewFinished(reason=FinishedReason.MODEL_DECIDED)


@pytest.mark.anyio
async def test_an_unexpected_decision_reply_is_a_bad_response():
    """A reply that is neither continue nor finish is rejected as a bad model response."""
    llm = FakeLLM("maybe later")
    config = ModelDecidesConfig(min_questions=3, max_questions=12)
    with pytest.raises(LLMResponseError):
        await is_finished(config, _turns(5), llm)
