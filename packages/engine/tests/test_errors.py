import pytest
from engine import UnusableQuestionError
from llm_gateway import LLMError


def test_unusable_question_error_is_an_llm_error():
    """The API's existing LLMError handler can route the engine's error without special cases."""
    assert issubclass(UnusableQuestionError, LLMError)


def test_unusable_question_error_is_retryable():
    """A fresh turn can produce a usable question, so the client may offer Retry."""
    assert UnusableQuestionError.retryable is True
    error = UnusableQuestionError(
        "The question failed a check.", failures=("too_long",), attempts=2
    )
    assert error.retryable is True


def test_unusable_question_error_carries_failed_checks_and_attempt_count():
    """The error reports which checks failed and how many question writes were tried."""
    error = UnusableQuestionError(
        "The question failed these checks: too_long, markdown.",
        failures=("too_long", "markdown"),
        attempts=2,
    )
    assert error.failures == ("too_long", "markdown")
    assert error.attempts == 2


def test_unusable_question_error_adds_no_text_to_its_message():
    """Its message is exactly the safe text the caller gave, with no input echoed by the error."""
    message = "The question failed these checks: too_long."
    error = UnusableQuestionError(message, failures=("too_long",), attempts=2)
    assert str(error) == message


def test_unusable_question_error_requires_both_details():
    """Failures and attempts are required keyword arguments, so callers cannot leave them out."""
    with pytest.raises(TypeError):
        UnusableQuestionError("The question failed a check.")
