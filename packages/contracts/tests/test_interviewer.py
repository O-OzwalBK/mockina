from typing import Any

import pytest
from contracts.interviewer import (
    MAX_QUESTION_TEXT_LENGTH,
    MAX_SKILL_ID_LENGTH,
    Question,
)
from pydantic import ValidationError

LENGTH_LIMITS = {"text": MAX_QUESTION_TEXT_LENGTH, "skill_id": MAX_SKILL_ID_LENGTH}

def valid_question_data() -> dict[str, Any]:
    """A fresh, valid question as a dictionary, for tests to modify."""
    return {
        "text": "What is a closure?",
        "skill_id": "javascript-closures",
        "difficulty": 2,
    }


def test_question_accepts_valid_values():
    """A question with text, a skill id, and a difficulty is valid."""
    question = Question.model_validate(valid_question_data())
    assert question.text == "What is a closure?"
    assert question.skill_id == "javascript-closures"
    assert question.difficulty == 2


@pytest.mark.parametrize("field", ["text", "skill_id"])
@pytest.mark.parametrize("blank", ["", "   "])
def test_question_rejects_blank_fields(field, blank):
    """Text and skill id cannot be empty or whitespace-only."""
    data = valid_question_data()
    data[field] = blank
    with pytest.raises(ValidationError):
        Question.model_validate(data)


@pytest.mark.parametrize("field", ["text", "skill_id", "difficulty"])
def test_question_requires_every_field_except_id(field):
    """Text, skill id, and difficulty are required; only the id is generated."""
    data = valid_question_data()
    del data[field]
    with pytest.raises(ValidationError):
        Question.model_validate(data)


@pytest.mark.parametrize("difficulty", [1, 3, 5])
def test_question_accepts_difficulty_in_range(difficulty):
    """Difficulty from 1 to 5 inclusive is valid, including both edges."""
    data = valid_question_data()
    data["difficulty"] = difficulty
    assert Question.model_validate(data).difficulty == difficulty


@pytest.mark.parametrize("difficulty", [0, 6, -1])
def test_question_rejects_difficulty_out_of_range(difficulty):
    """Difficulty below 1 or above 5 is invalid."""
    data = valid_question_data()
    data["difficulty"] = difficulty
    with pytest.raises(ValidationError):
        Question.model_validate(data)


def test_question_rejects_fractional_difficulty():
    """Difficulty is a whole number, so 2.5 is invalid."""
    data = valid_question_data()
    data["difficulty"] = 2.5
    with pytest.raises(ValidationError):
        Question.model_validate(data)


def test_question_generates_unique_ids():
    """Each question gets its own id automatically, so ids never collide across sessions."""
    first = Question.model_validate(valid_question_data())
    second = Question.model_validate(valid_question_data())
    assert first.id != second.id


def test_question_rejects_invalid_id():
    """An explicit id must be a valid UUID, so labels like 'q-1' are rejected."""
    data = valid_question_data()
    data["id"] = "q-1"
    with pytest.raises(ValidationError):
        Question.model_validate(data)


def test_question_strips_surrounding_whitespace():
    """Spaces around a text field are removed rather than stored."""
    data = valid_question_data()
    data["text"] = "  What is a closure?  "
    assert Question.model_validate(data).text == "What is a closure?"


@pytest.mark.parametrize("field", LENGTH_LIMITS)
def test_question_accepts_maximum_length(field):
    """Text exactly at the length limit is valid."""
    data = valid_question_data()
    data[field] = "a" * LENGTH_LIMITS[field]
    Question.model_validate(data)


@pytest.mark.parametrize("field", LENGTH_LIMITS)
def test_question_rejects_over_maximum_length(field):
    """Text one character over the length limit is invalid."""
    data = valid_question_data()
    data[field] = "a" * (LENGTH_LIMITS[field] + 1)
    with pytest.raises(ValidationError):
        Question.model_validate(data)


def test_question_is_immutable():
    """A question cannot be changed after creation."""
    question = Question.model_validate(valid_question_data())
    with pytest.raises(ValidationError):
        question.text = "changed"


def test_question_rejects_unknown_fields():
    """Unknown fields are rejected so typos are not silently ignored."""
    data = valid_question_data()
    data["colour"] = "red"
    with pytest.raises(ValidationError):
        Question.model_validate(data)