import pytest
from contracts.interviewer import Question
from pydantic import ValidationError


def valid_question_data() -> dict:
    """A fresh, valid question as a dictionary, for tests to modify."""
    return {"text": "What is a closure?", "topic": "JavaScript"}

def test_question_accepts_valid_values():
    """A question with an id, text, and topic is valid."""
    question = Question.model_validate(valid_question_data())
    assert question.text == "What is a closure?"


@pytest.mark.parametrize("field", ["text", "topic"])
@pytest.mark.parametrize("blank", ["", "   "])
def test_question_rejects_blank_fields(field, blank):
    """Text and topic cannot be empty or whitespace-only."""
    data = valid_question_data()
    data[field] = blank
    with pytest.raises(ValidationError):
        Question.model_validate(data)


@pytest.mark.parametrize("field", ["text", "topic"])
def test_question_requires_text_and_topic(field):
    """Text and topic are required."""
    data = valid_question_data()
    del data[field]
    with pytest.raises(ValidationError):
        Question.model_validate(data)


def test_question_strips_surrounding_whitespace():
    """Spaces around a text field are removed rather than stored."""
    data = valid_question_data()
    data["text"] = "  What is a closure?  "
    assert Question.model_validate(data).text == "What is a closure?"

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