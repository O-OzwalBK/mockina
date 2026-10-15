import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence

from llm_gateway.errors import LLMError, LLMRateLimitError
from llm_gateway.interface import LLM
from llm_gateway.models import ChatMessage, Completion

# Doubling the delay more than this many times could overflow a float, and by then the
# cap has long since stopped the delay from growing.
MAX_DOUBLINGS = 30


class RetryingLLM:
    """An LLM that tries again after a pause when the one it wraps fails for a temporary reason.

    Wrap any `LLM` with it and use it in its place.
    A failure is retried only if its error says `retryable`.
    Each pause doubles, from `base_delay_seconds` up to `max_delay_seconds`, and is scaled by a random factor so that many clients do not all retry at the same instant.
    If the provider asked for a specific wait, that wait is used instead, unless it is longer than `max_delay_seconds`: then the error is raised straight away, because a person is waiting for the answer.
    After the last retry the original error is raised, so callers can still catch the specific type.

    `sleep` and `jitter` can be replaced, which lets tests run without really waiting.
    """

    def __init__(
        self,
        llm: LLM,
        *,
        max_retries: int,
        base_delay_seconds: float = 0.5,
        max_delay_seconds: float = 8.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative.Use 0 for no retries.")
        if base_delay_seconds < 0:
            raise ValueError("base_delay_seconds cannot be negative.")
        if max_delay_seconds < base_delay_seconds:
            raise ValueError("max_delay_seconds cannot be smaller than base_delay_seconds.")
        self._llm = llm
        self._max_retries = max_retries
        self._base_delay_seconds = base_delay_seconds
        self._max_delay_seconds = max_delay_seconds
        self._sleep = sleep
        self._jitter = jitter

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ) -> Completion:
        """Send the conversation to the wrapped LLM, retrying temporary failures.

        Makes at most `max_retries + 1` attempts and raises the last error if none works.
        """

        retries_so_far = 0
        while True:
            try:
                return await self._llm.complete(
                    messages, temperature=temperature, max_output_tokens=max_output_tokens
                )
            except LLMError as error:
                if not error.retryable or retries_so_far >= self._max_retries:
                    raise
                delay = self.delay_before_retry(error, retries_so_far)
                if delay is None:
                    raise
                retries_so_far += 1
                await self._sleep(delay)

    def delay_before_retry(self, error: LLMError, retries_so_far: int) -> float | None:
        """Determine how long to pause before the next attempt, or None if we should not wait at all."""

        if isinstance(error, LLMRateLimitError) and error.retry_after is not None:
            if error.retry_after > self._max_delay_seconds:
                return None
            return error.retry_after
        doublings = min(retries_so_far, MAX_DOUBLINGS)
        full_delay = min(self._max_delay_seconds, self._base_delay_seconds * 2**doublings)
        return self._jitter() * full_delay
