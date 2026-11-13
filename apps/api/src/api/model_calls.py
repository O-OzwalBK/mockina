"""Wrappers around the model that log safe metadata for model calls made by developer routes or count its usage."""

import logging
from collections.abc import Sequence
from time import perf_counter

from llm_gateway import LLM, ChatMessage, Completion, LLMError


class LoggedLLM:
    """Forward model calls while logging outcome and usage, never any content."""

    def __init__(self, llm: LLM, *, model_name: str, logger: logging.Logger) -> None:
        """Wrap one model for one developer request, logging through the caller's logger."""
        self._llm = llm
        self._model_name = model_name
        self._logger = logger

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ) -> Completion:
        """Forward one model call and log only its outcome and usage metadata."""
        started = perf_counter()
        try:
            completion = await self._llm.complete(
                messages,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        except LLMError as error:
            elapsed_ms = int((perf_counter() - started) * 1000)
            self._logger.info(
                "model_call outcome=%s model=%s elapsed_ms=%d "
                "prompt_tokens=unknown completion_tokens=unknown",
                type(error).__name__,
                self._model_name,
                elapsed_ms,
            )
            raise

        elapsed_ms = int((perf_counter() - started) * 1000)
        self._logger.info(
            "model_call outcome=ok model=%s elapsed_ms=%d prompt_tokens=%s completion_tokens=%s",
            completion.model,
            elapsed_ms,
            completion.prompt_tokens,
            completion.completion_tokens,
        )
        return completion


class MeteredLLM:
    """Forward the model calls of one job and add up their usage, keeping no content.

    A job such as "write the next question" may call the model several times (extract the
    skills, write the question, repair it). The job creates one MeteredLLM, passes it to the
    engine in place of the real model, and afterwards logs one line with the totals.
    """

    def __init__(self, llm: LLM) -> None:
        """Wrap the model for one job."""
        self._llm = llm
        self.calls = 0
        """How many times the model was asked, including attempts that failed."""
        self.prompt_tokens: int | None = None
        """Prompt tokens the provider reported, added up; None if it reported none."""
        self.completion_tokens: int | None = None
        """Reply tokens the provider reported, added up; None if it reported none."""

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ) -> Completion:
        """Forward one call, count it, and add up the tokens it reports."""
        self.calls += 1
        completion = await self._llm.complete(
            messages,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        if completion.prompt_tokens is not None:
            self.prompt_tokens = (self.prompt_tokens or 0) + completion.prompt_tokens
        if completion.completion_tokens is not None:
            self.completion_tokens = (self.completion_tokens or 0) + completion.completion_tokens
        return completion