"""A fake language model for tests.

Import it with `from llm_gateway.testing import FakeLLM`.
It is deliberately not part of the package's top-level names: production code has no use for it, and keeping it in its own module means it cannot be picked up by mistake.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from llm_gateway.models import ChatMessage, Completion

FAKE_MODEL_NAME = "fake-model"


class ScriptExhaustedError(AssertionError):
    """The code under test asked a FakeLLM for more replies than the test scripted.

    It is an AssertionError and not an LLMError on purpose. Code that catches LLMError to handle a failing model must not swallow a mistake in the test itself.
    """


@dataclass(frozen=True)
class RecordedCall:
    """One call made to a FakeLLM, kept so a test can check what was sent."""

    messages: tuple[ChatMessage, ...]
    """The conversation, copied at the moment of the call."""

    temperature: float
    """The temperature given, or the default of 0.2."""

    max_output_tokens: int | None
    """The reply limit given, or None for the default."""


class FakeLLM:
    """An LLM that plays back a script instead of calling a model.

    Give it the outcomes you want, in order, and it hands out one per call.
    An outcome is a string (shorthand for a successful reply with that text), a `Completion`, or an exception, which is raised.
    Every call is recorded in `calls`, including calls that fail.
    A call beyond the end of the script raises `ScriptExhaustedError`, so a code path that asks the model more often than the test expected cannot go unnoticed.
    """

    def __init__(self, *script: str | Completion | BaseException) -> None:
        # Strings become Completions here and not at call time, so an invalid reply (an
        # empty string) fails on the line that built the script.
        self._script: tuple[Completion | BaseException, ...] = tuple(
            Completion(text=item, model=FAKE_MODEL_NAME) if isinstance(item, str) else item
            for item in script
        )
        self.calls: list[RecordedCall] = []

    @property
    def remaining(self) -> int:
        """How many scripted outcomes have not been used yet."""
        return max(0, len(self._script) - len(self.calls))

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ) -> Completion:
        """Record the call, then play back the next scripted outcome."""
        self.calls.append(
            RecordedCall(
                messages=tuple(messages),
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        )
        call_number = len(self.calls)
        if call_number > len(self._script):
            raise ScriptExhaustedError(
                f"FakeLLM was asked for reply number {call_number}, but the script holds "
                f"{len(self._script)}. Add more outcomes to the script, or find out why the "
                "code under test asked again."
            )
        outcome = self._script[call_number - 1]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
