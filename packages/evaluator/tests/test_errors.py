import pytest
from evaluator import EvaluationError
from llm_gateway import LLMError


def test_evaluation_error_is_an_llm_error():
    """The API's existing LLMError handler can route a failed grade without special cases."""
    assert issubclass(EvaluationError, LLMError)


def test_evaluation_error_is_not_retryable():
    """Grading is a background job; a failure is retried through the regrade path, not automatically."""
    assert EvaluationError.retryable is False
    error = EvaluationError(
        "The model did not produce a usable evaluation.",
        failures=("invalid_score",),
        attempts=2,
    )
    assert error.retryable is False


def test_evaluation_error_carries_failed_checks_and_attempt_count():
    """The error reports which checks failed and how many grading calls were tried."""
    error = EvaluationError(
        "The model did not produce a usable evaluation.",
        failures=("missing_metric", "invalid_score"),
        attempts=2,
    )
    assert error.failures == ("missing_metric", "invalid_score")
    assert error.attempts == 2


def test_evaluation_error_adds_no_text_to_its_message():
    """The message is exactly the safe text the caller gave, with no answer echoed by the error."""
    message = "The model did not produce a usable evaluation."
    error = EvaluationError(message, failures=("invalid_json",), attempts=2)
    assert str(error) == message


def test_evaluation_error_requires_both_details():
    """Failures and attempts are required keyword arguments, so callers cannot leave them out."""
    with pytest.raises(TypeError):
        EvaluationError("The model did not produce a usable evaluation.")  # pyright: ignore[reportCallIssue]
