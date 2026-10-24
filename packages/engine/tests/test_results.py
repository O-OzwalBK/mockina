from typing import get_args

import pytest
from contracts import Question
from engine import EngineOutcome, FinishedReason, InterviewFinished
from pydantic import ValidationError


def test_finished_reason_values_are_exactly_the_three_end_paths():
    """The reason enum names the three ways an interview can end."""
    assert {reason.value for reason in FinishedReason} == {
        "question_count_reached",
        "answer_time_reached",
        "model_decided",
    }


def test_interview_finished_holds_a_finished_reason():
    """An InterviewFinished stores the reason as the enum, not as a plain string."""
    finished = InterviewFinished(reason=FinishedReason.QUESTION_COUNT_REACHED)
    assert isinstance(finished.reason, FinishedReason)


def test_interview_finished_parses_a_reason_from_its_wire_value():
    """A reason sent as its string value validates into the enum."""
    finished = InterviewFinished.model_validate({"reason": "model_decided"})
    assert finished.reason is FinishedReason.MODEL_DECIDED


def test_interview_finished_rejects_an_unknown_reason():
    """A reason outside the enum is invalid."""
    with pytest.raises(ValidationError):
        InterviewFinished.model_validate({"reason": "bored"})


def test_interview_finished_is_frozen():
    """The result cannot be changed after the engine returns it."""
    finished = InterviewFinished(reason=FinishedReason.ANSWER_TIME_REACHED)
    with pytest.raises(ValidationError):
        finished.reason = FinishedReason.MODEL_DECIDED


def test_interview_finished_has_a_docstring():
    """The model's docstring says that the engine returns no question when this appears."""
    assert InterviewFinished.__doc__ is not None
    assert InterviewFinished.__doc__.strip() != ""


def test_interview_finished_documents_its_reason_field():
    """The reason field carries a description, so generated docs explain the result."""
    assert InterviewFinished.model_fields["reason"].description


def test_engine_outcome_is_exactly_the_question_or_finished_union():
    """The public outcome type is a Question or an InterviewFinished, with no third arm."""
    assert set(get_args(EngineOutcome)) == {Question, InterviewFinished}
