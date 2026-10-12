import pytest
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

ALL_ERRORS = [
    ContextBudgetExceededError,
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMServerError,
    LLMTimeoutError,
]


@pytest.mark.parametrize("error_class", ALL_ERRORS, ids=lambda cls: cls.__name__)
def test_every_gateway_error_is_an_llm_error(error_class):
    """Callers can catch LLMError to handle every failure the gateway can raise."""
    assert issubclass(error_class, LLMError)


@pytest.mark.parametrize(
    ("error_class", "retryable"),
    [
        (LLMConnectionError, True),
        (LLMTimeoutError, True),
        (LLMRateLimitError, True),
        (LLMServerError, True),
        (LLMAuthError, False),
        (LLMRequestError, False),
        (LLMResponseError, False),
        (ContextBudgetExceededError, False),
    ],
    ids=lambda value: value.__name__ if isinstance(value, type) else str(value),
)
def test_only_temporary_problems_are_marked_retryable(error_class, retryable):
    """Network, timeout, rate-limit, and server errors may succeed on a retry; the rest never will."""
    assert error_class.retryable is retryable


def test_the_base_error_is_not_retryable():
    """An unclassified error is not retried, to avoid repeating a request that may be harmful."""
    assert LLMError.retryable is False


def test_an_error_message_is_what_str_shows():
    """The message given when raising the error is the text people see."""
    assert str(LLMAuthError("The provider rejected the API key.")) == (
        "The provider rejected the API key."
    )


def test_rate_limit_error_remembers_how_long_to_wait():
    """A rate-limit error carries the wait time the provider asked for."""
    error = LLMRateLimitError("Too many requests.", retry_after=2.5)
    assert error.retry_after == 2.5


def test_rate_limit_wait_time_defaults_to_unknown():
    """When the provider does not say how long to wait, the wait time is None."""
    assert LLMRateLimitError("Too many requests.").retry_after is None


def test_context_error_carries_the_numbers_when_we_know_them():
    """A context error from our own estimate reports the estimate and the available budget."""
    error = ContextBudgetExceededError(
        "Prompt too long.", estimated_tokens=9000, budget_tokens=7000
    )
    assert error.estimated_tokens == 9000
    assert error.budget_tokens == 7000


def test_context_error_numbers_default_to_unknown():
    """When the provider reported the problem, we have no estimate, so both numbers are None."""
    error = ContextBudgetExceededError("Prompt too long.")
    assert error.estimated_tokens is None
    assert error.budget_tokens is None
