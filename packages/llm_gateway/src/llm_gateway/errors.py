from typing import ClassVar


class LLMError(Exception):
    """Base class for every error the gateway raises.

    Messages are safe to log and to show to people: they never contain the API key
    or any part of the prompt. `retryable` says whether trying the same request
    again might succeed.
    """

    retryable: ClassVar[bool] = False


class LLMConnectionError(LLMError):
    """The model server could not be reached: it is down, the address is wrong, or there is no network."""

    retryable: ClassVar[bool] = True


class LLMTimeoutError(LLMError):
    """The model server did not answer within the time limit."""

    retryable: ClassVar[bool] = True


class LLMRateLimitError(LLMError):
    """The provider said we are sending requests too fast (HTTP 429)."""

    retryable: ClassVar[bool] = True

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        """Seconds the provider asked us to wait before trying again, or None if it did not say."""


class LLMServerError(LLMError):
    """The provider had a problem on its side (HTTP 500 and above)."""

    retryable: ClassVar[bool] = True


class LLMAuthError(LLMError):
    """The provider rejected the API key (HTTP 401 or 403). Trying again will not help."""


class LLMRequestError(LLMError):
    """The provider rejected the request itself, for example an unknown model name. Trying again will not help."""


class LLMResponseError(LLMError):
    """The provider answered, but the reply was not in the expected shape or had no text."""


class ContextBudgetExceededError(LLMError):
    """The prompt is too long for the model's context window, leaving no room for the reply."""

    def __init__(
        self,
        message: str,
        *,
        estimated_tokens: int | None = None,
        budget_tokens: int | None = None,
    ) -> None:
        super().__init__(message)
        self.estimated_tokens = estimated_tokens
        """Our estimate of the prompt size in tokens, or None if the provider told us it was too long."""
        self.budget_tokens = budget_tokens
        """Tokens available for the prompt after reserving room for the reply, or None if unknown."""
