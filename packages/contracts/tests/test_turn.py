from itertools import product
from typing import Any

import pytest
from contracts.turn import MAX_GRADING_ERROR_LENGTH, Turn, TurnStatus
from pydantic import ValidationError

QUESTION_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
OTHER_QUESTION_ID = "9c1d2e3f-4a5b-4c6d-8e7f-0a1b2c3d4e5f"
GRADING_ERROR = "The provider timed out."
METRICS = ["correctness", "depth", "clarity", "relevance"]

# The four combinations the design allows: (status, has_answer, has_evaluation, has_error).
# Written out separately from the model so the tests check the rules independently.
VALID_COMBINATIONS = [
    (TurnStatus.AWAITING_ANSWER, False, False, False),
    (TurnStatus.AWAITING_GRADE, True, False, False),
    (TurnStatus.GRADED, True, True, False),
    (TurnStatus.GRADING_FAILED, True, False, True),
]
ALL_COMBINATIONS = list(product(TurnStatus, [False, True], [False, True], [False, True]))
INVALID_COMBINATIONS = [c for c in ALL_COMBINATIONS if c not in VALID_COMBINATIONS]


def valid_question_data() -> dict[str, Any]:
    """A fresh, valid question as a dictionary."""
    return {
        "id": QUESTION_ID,
        "text": "What is a closure?",
        "skill_id": "skill-1",
        "difficulty": 2,
    }


def valid_answer_data() -> dict[str, Any]:
    """A fresh, valid answer as a dictionary."""
    return {"transcript": "A closure remembers variables from its scope.", "duration": 6.5}


def valid_evaluation_data(question_id: str = QUESTION_ID) -> dict[str, Any]:
    """A fresh, valid evaluation as a dictionary."""
    data: dict[str, Any] = {"question_id": question_id, "summary": "Good answer."}
    for metric in METRICS:
        data[metric] = {"score": 7, "feedback": "Reasonable."}
    return data


def build_turn_data(
    status: TurnStatus,
    has_answer: bool = False,
    has_evaluation: bool = False,
    has_error: bool = False,
) -> dict[str, Any]:
    """Build turn data containing only the parts asked for."""
    data: dict[str, Any] = {"question": valid_question_data(), "status": status}
    if has_answer:
        data["answer"] = valid_answer_data()
    if has_evaluation:
        data["evaluation"] = valid_evaluation_data()
    if has_error:
        data["grading_error"] = GRADING_ERROR
    return data


def new_turn() -> Turn:
    """A brand-new turn that has only been asked."""
    return Turn.model_validate({"question": valid_question_data()})


# --- Life-cycle rules ---


def test_turn_needs_only_a_question_to_start():
    """A new turn needs just a question and starts as awaiting_answer with nothing else set."""
    turn = new_turn()
    assert turn.status == TurnStatus.AWAITING_ANSWER
    assert turn.answer is None
    assert turn.evaluation is None
    assert turn.grading_error is None


@pytest.mark.parametrize("status, has_answer, has_evaluation, has_error", VALID_COMBINATIONS)
def test_turn_accepts_valid_lifecycle_states(status, has_answer, has_evaluation, has_error):
    """Each status is valid with exactly the parts the life cycle requires for it."""
    data = build_turn_data(status, has_answer, has_evaluation, has_error)
    assert Turn.model_validate(data).status == status


@pytest.mark.parametrize("status, has_answer, has_evaluation, has_error", INVALID_COMBINATIONS)
def test_turn_rejects_invalid_lifecycle_states(status, has_answer, has_evaluation, has_error):
    """Every other mix of status, answer, evaluation, and error is rejected."""
    data = build_turn_data(status, has_answer, has_evaluation, has_error)
    with pytest.raises(ValidationError):
        Turn.model_validate(data)


def test_turn_rejects_evaluation_for_a_different_question():
    """An evaluation must grade this turn's own question."""
    data = build_turn_data(TurnStatus.GRADED, has_answer=True)
    data["evaluation"] = valid_evaluation_data(question_id=OTHER_QUESTION_ID)
    with pytest.raises(ValidationError):
        Turn.model_validate(data)


def test_turn_accepts_a_silent_answer():
    """A user who stays silent still considered an answer: an empty transcript is valid."""
    data = build_turn_data(TurnStatus.AWAITING_GRADE, has_answer=True)
    data["answer"]["transcript"] = ""
    turn = Turn.model_validate(data)
    assert turn.answer is not None
    assert turn.answer.transcript == ""


def test_turn_rejects_unknown_status():
    """Only the four defined statuses are valid."""
    data = build_turn_data(TurnStatus.AWAITING_ANSWER)
    data["status"] = "done"
    with pytest.raises(ValidationError):
        Turn.model_validate(data)


def test_turn_rejects_unknown_fields():
    """Unknown fields are rejected so typos are not silently ignored."""
    data = build_turn_data(TurnStatus.AWAITING_ANSWER)
    data["anwser"] = valid_answer_data()
    with pytest.raises(ValidationError):
        Turn.model_validate(data)


# --- Grading error ---


@pytest.mark.parametrize("blank", ["", "   "])
def test_turn_rejects_blank_grading_error(blank):
    """A failed turn needs a real reason, not an empty one."""
    data = build_turn_data(TurnStatus.GRADING_FAILED, has_answer=True)
    data["grading_error"] = blank
    with pytest.raises(ValidationError):
        Turn.model_validate(data)


def test_turn_accepts_grading_error_at_maximum_length():
    """A grading error exactly at the length limit is valid."""
    data = build_turn_data(TurnStatus.GRADING_FAILED, has_answer=True)
    data["grading_error"] = "a" * MAX_GRADING_ERROR_LENGTH
    Turn.model_validate(data)


def test_turn_rejects_grading_error_over_maximum_length():
    """A grading error one character over the limit is invalid."""
    data = build_turn_data(TurnStatus.GRADING_FAILED, has_answer=True)
    data["grading_error"] = "a" * (MAX_GRADING_ERROR_LENGTH + 1)
    with pytest.raises(ValidationError):
        Turn.model_validate(data)


# --- Immutability and updated() ---


def test_turn_nested_models_cannot_be_changed():
    """The question inside a turn is immutable too, so a validated turn cannot be altered from outside."""
    turn = new_turn()
    with pytest.raises(ValidationError):
        turn.question.text = "changed"


def test_turn_is_immutable():
    """Fields cannot be assigned after creation, so a turn cannot skip validation."""
    turn = new_turn()
    with pytest.raises(ValidationError):
        turn.status = TurnStatus.GRADED


def test_turn_updated_moves_to_the_next_state():
    """updated() returns a new turn in the next state and leaves the original unchanged."""
    original = new_turn()
    answered = original.updated(status=TurnStatus.AWAITING_GRADE, answer=valid_answer_data())
    assert answered.status == TurnStatus.AWAITING_GRADE
    assert answered.answer is not None
    assert original.status == TurnStatus.AWAITING_ANSWER
    assert original.answer is None


def test_turn_updated_rejects_invalid_transitions():
    """updated() refuses a change that breaks the life-cycle rules, such as graded with no evaluation."""
    with pytest.raises(ValidationError):
        new_turn().updated(status=TurnStatus.GRADED)


def test_turn_updated_rejects_unknown_fields():
    """A typo in an updated() argument raises an error instead of doing nothing."""
    with pytest.raises(ValidationError):
        new_turn().updated(anwser=valid_answer_data())


def test_turn_can_retry_after_failed_grading():
    """A failed turn goes back to awaiting_grade once its error is cleared."""
    failed = Turn.model_validate(
        build_turn_data(TurnStatus.GRADING_FAILED, has_answer=True, has_error=True)
    )
    retry = failed.updated(status=TurnStatus.AWAITING_GRADE, grading_error=None)
    assert retry.status == TurnStatus.AWAITING_GRADE
    assert retry.grading_error is None


def test_turn_walks_through_the_full_lifecycle():
    """A turn can move from asked, to answered, to graded using updated() at each step."""
    turn = new_turn()
    turn = turn.updated(status=TurnStatus.AWAITING_GRADE, answer=valid_answer_data())
    turn = turn.updated(status=TurnStatus.GRADED, evaluation=valid_evaluation_data())
    assert turn.status == TurnStatus.GRADED
    assert turn.evaluation is not None
