from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from contracts.session import MAX_TURNS_PER_SESSION, InterviewSession, SessionStatus
from contracts.turn import Turn, TurnStatus
from pydantic import ValidationError

PREPARATION_ID = "9c1d2e3f-4a5b-4c6d-8e7f-0a1b2c3d4e5f"
START = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
LATER = START + timedelta(minutes=30)
EARLIER = START - timedelta(minutes=1)

# (status, has_end_time) combinations the rules allow and reject.
VALID_STATUS_AND_END = [
    (SessionStatus.IN_PROGRESS, False),
    (SessionStatus.COMPLETED, True),
    (SessionStatus.ABANDONED, True),
]
INVALID_STATUS_AND_END = [
    (SessionStatus.IN_PROGRESS, True),
    (SessionStatus.COMPLETED, False),
    (SessionStatus.ABANDONED, False),
]


def make_turn_data(status: TurnStatus = TurnStatus.AWAITING_GRADE) -> dict[str, Any]:
    """A fresh turn in the given status, as a dictionary, with its own unique question id."""
    question_id = str(uuid4())
    data: dict[str, Any] = {
        "question": {
            "id": question_id,
            "text": "What is a closure?",
            "skill_id": "skill-1",
            "difficulty": 2,
        },
        "status": status,
    }
    if status != TurnStatus.AWAITING_ANSWER:
        data["answer"] = {"transcript": "A closure remembers its scope.", "duration": 5.0}
    if status == TurnStatus.GRADED:
        scores = {"score": 7, "feedback": "Reasonable."}
        data["evaluation"] = {
            "question_id": question_id,
            "summary": "Good answer.",
            "correctness": scores,
            "depth": scores,
            "clarity": scores,
            "relevance": scores,
        }
    if status == TurnStatus.GRADING_FAILED:
        data["grading_error"] = "The provider timed out."
    return data


def session_data(
    status: SessionStatus = SessionStatus.IN_PROGRESS, ended: bool = False
) -> dict[str, Any]:
    """Valid session data with one answered turn, ended or not, for tests to modify."""
    data: dict[str, Any] = {
        "preparation_id": PREPARATION_ID,
        "status": status,
        "started_at": START,
        "updated_at": LATER if ended else START,
        "turns": [make_turn_data(TurnStatus.AWAITING_GRADE)],
    }
    if ended:
        data["ended_at"] = LATER
    return data


# --- Basics and defaults ---


def test_session_needs_only_a_preparation_id():
    """A new session needs just a preparation id; everything else has a sensible default."""
    session = InterviewSession.model_validate({"preparation_id": PREPARATION_ID})
    assert session.status == SessionStatus.IN_PROGRESS
    assert session.ended_at is None
    assert session.turns == ()
    assert session.started_at.utcoffset() == timedelta(0)


def test_session_generates_unique_ids():
    """Each session gets its own id automatically."""
    first = InterviewSession.model_validate({"preparation_id": PREPARATION_ID})
    second = InterviewSession.model_validate({"preparation_id": PREPARATION_ID})
    assert first.id != second.id


def test_session_requires_preparation_id():
    """A session must say which preparation it belongs to."""
    with pytest.raises(ValidationError):
        InterviewSession.model_validate({})


def test_session_rejects_invalid_preparation_id():
    """The preparation id must be a valid UUID."""
    with pytest.raises(ValidationError):
        InterviewSession.model_validate({"preparation_id": "p-1"})


def test_session_rejects_unknown_status():
    """Only the three defined statuses are valid."""
    data = session_data()
    data["status"] = "paused"
    with pytest.raises(ValidationError):
        InterviewSession.model_validate(data)


# --- Status and end time ---


@pytest.mark.parametrize("status, ended", VALID_STATUS_AND_END)
def test_session_accepts_end_time_that_matches_status(status, ended):
    """In-progress sessions have no end time; completed and abandoned sessions have one."""
    session = InterviewSession.model_validate(session_data(status, ended))
    assert session.status == status


@pytest.mark.parametrize("status, ended", INVALID_STATUS_AND_END)
def test_session_rejects_end_time_that_contradicts_status(status, ended):
    """An in-progress session with an end time, or a finished one without, is invalid."""
    with pytest.raises(ValidationError):
        InterviewSession.model_validate(session_data(status, ended))


# --- Time order ---


def test_session_accepts_equal_times():
    """Start, end, and update times may all be equal."""
    data = session_data(SessionStatus.ABANDONED, ended=True)
    data["ended_at"] = START
    data["updated_at"] = START
    InterviewSession.model_validate(data)


def test_session_rejects_end_before_start():
    """A session cannot end before it started."""
    data = session_data(SessionStatus.ABANDONED, ended=True)
    data["ended_at"] = EARLIER
    with pytest.raises(ValidationError):
        InterviewSession.model_validate(data)


def test_session_rejects_update_before_start():
    """A session cannot have been updated before it started."""
    data = session_data()
    data["updated_at"] = EARLIER
    with pytest.raises(ValidationError):
        InterviewSession.model_validate(data)


def test_session_rejects_update_before_end():
    """The last update cannot be earlier than the end time."""
    data = session_data(SessionStatus.ABANDONED, ended=True)
    data["updated_at"] = START
    with pytest.raises(ValidationError):
        InterviewSession.model_validate(data)


# --- Turns ---

def test_session_accepts_maximum_number_of_turns():
    """A session with exactly the maximum number of turns is valid."""
    data = session_data()
    data["turns"] = [make_turn_data() for _ in range(MAX_TURNS_PER_SESSION)]
    InterviewSession.model_validate(data)


def test_session_rejects_too_many_turns():
    """A session with one turn more than the maximum is invalid."""
    data = session_data()
    data["turns"] = [make_turn_data() for _ in range(MAX_TURNS_PER_SESSION + 1)]
    with pytest.raises(ValidationError):
        InterviewSession.model_validate(data)

        
def test_session_rejects_duplicate_questions():
    """The same question cannot appear in two turns."""
    data = session_data()
    turn = make_turn_data()
    data["turns"] = [turn, turn]
    with pytest.raises(ValidationError):
        InterviewSession.model_validate(data)


def test_session_accepts_open_question_as_last_turn():
    """The last turn may still be waiting for an answer."""
    data = session_data()
    data["turns"] = [make_turn_data(TurnStatus.AWAITING_GRADE), make_turn_data(TurnStatus.AWAITING_ANSWER)]
    InterviewSession.model_validate(data)


def test_session_rejects_open_question_before_the_last_turn():
    """Only one question can be open at a time: an unanswered turn must be the last."""
    data = session_data()
    data["turns"] = [make_turn_data(TurnStatus.AWAITING_ANSWER), make_turn_data(TurnStatus.AWAITING_GRADE)]
    with pytest.raises(ValidationError):
        InterviewSession.model_validate(data)


def test_session_rejects_completed_without_turns():
    """A completed session must have at least one turn."""
    data = session_data(SessionStatus.COMPLETED, ended=True)
    data["turns"] = []
    with pytest.raises(ValidationError):
        InterviewSession.model_validate(data)


def test_session_rejects_completed_with_unanswered_question():
    """A completed session cannot end with a question the user never answered."""
    data = session_data(SessionStatus.COMPLETED, ended=True)
    data["turns"] = [make_turn_data(TurnStatus.AWAITING_GRADE), make_turn_data(TurnStatus.AWAITING_ANSWER)]
    with pytest.raises(ValidationError):
        InterviewSession.model_validate(data)


def test_session_allows_abandoned_with_unanswered_question():
    """A user who leaves mid-question leaves an abandoned session with an open question."""
    data = session_data(SessionStatus.ABANDONED, ended=True)
    data["turns"] = [make_turn_data(TurnStatus.AWAITING_GRADE), make_turn_data(TurnStatus.AWAITING_ANSWER)]
    InterviewSession.model_validate(data)


def test_session_allows_abandoned_without_turns():
    """A user who leaves before the first question leaves an abandoned session with no turns."""
    data = session_data(SessionStatus.ABANDONED, ended=True)
    data["turns"] = []
    InterviewSession.model_validate(data)


@pytest.mark.parametrize(
    "last_status",
    [TurnStatus.AWAITING_GRADE, TurnStatus.GRADING_FAILED, TurnStatus.GRADED],
)
def test_session_completed_does_not_wait_for_grading(last_status):
    """Completed means the interview ended, not that grading finished, so ungraded turns are allowed."""
    data = session_data(SessionStatus.COMPLETED, ended=True)
    data["turns"] = [make_turn_data(last_status)]
    InterviewSession.model_validate(data)


# --- Datetimes ---


@pytest.mark.parametrize("field", ["started_at", "ended_at", "updated_at"])
def test_session_rejects_naive_datetimes(field):
    """Times without a timezone are invalid."""
    data = session_data(SessionStatus.ABANDONED, ended=True)
    data[field] = "2026-10-04T09:00:00"
    with pytest.raises(ValidationError):
        InterviewSession.model_validate(data)


def test_session_converts_times_to_utc():
    """Times sent with another offset are converted to UTC."""
    data = session_data()
    data["started_at"] = "2026-10-04T14:45:00+05:45"
    data["updated_at"] = "2026-10-04T14:45:00+05:45"
    session = InterviewSession.model_validate(data)
    assert session.started_at.utcoffset() == timedelta(0)
    assert session.started_at == START


# --- Immutability and updated() ---


def test_session_turns_are_a_tuple():
    """Turns are stored as a tuple, so they cannot be appended to in place."""
    session = InterviewSession.model_validate(session_data())
    assert isinstance(session.turns, tuple)


def test_session_fields_cannot_be_assigned():
    """Fields cannot be assigned after creation, so a session cannot skip validation."""
    session = InterviewSession.model_validate(session_data())
    with pytest.raises(ValidationError):
        session.status = SessionStatus.COMPLETED


def test_session_updated_adds_a_turn():
    """updated() returns a session with the new turn added and leaves the original unchanged."""
    session = InterviewSession.model_validate(session_data())
    new_turn = Turn.model_validate(make_turn_data(TurnStatus.AWAITING_ANSWER))
    changed = session.updated(turns=session.turns + (new_turn,))
    assert len(changed.turns) == 2
    assert len(session.turns) == 1


def test_session_updated_rejects_invalid_changes():
    """updated() refuses a change that breaks the rules, such as completing without an end time."""
    session = InterviewSession.model_validate(session_data())
    with pytest.raises(ValidationError):
        session.updated(status=SessionStatus.COMPLETED)


def test_session_walks_through_a_full_interview():
    """A session can go from started, to asked, to answered, to completed using updated() at each step."""
    session = InterviewSession.model_validate(
        {"preparation_id": PREPARATION_ID, "started_at": START, "updated_at": START}
    )
    asked = Turn.model_validate(make_turn_data(TurnStatus.AWAITING_ANSWER))
    session = session.updated(turns=(asked,))

    answered = asked.updated(
        status=TurnStatus.AWAITING_GRADE,
        answer={"transcript": "A closure remembers its scope.", "duration": 5.0},
    )
    session = session.updated(turns=(answered,))

    session = session.updated(status=SessionStatus.COMPLETED, ended_at=LATER, updated_at=LATER)
    assert session.status == SessionStatus.COMPLETED
    assert session.turns[0].status == TurnStatus.AWAITING_GRADE