"""The engine's own failure: the model could not write a usable question."""

from typing import ClassVar

from llm_gateway import LLMError


class EmptySkillGraphError(ValueError):
    """The engine was given a skill graph with no leaf skills to ask about."""


class UnusableQuestionError(LLMError):
    """The model did not produce a usable question after one corrective retry.

    The failed checks are carried as names, so this error never repeats the
    question text, the prompt, the job description, or the resume. The API maps it
    to a retryable bad-response error, which lets the client offer Retry.
    """

    retryable: ClassVar[bool] = True

    def __init__(
        self,
        message: str,
        *,
        failures: tuple[str, ...],
        attempts: int,
    ) -> None:
        """Record the failed checks and how many question writes were tried."""
        super().__init__(message)
        self.failures = failures
        """Names of the checks the model's text failed."""
        self.attempts = attempts
        """How many question writes were tried, including the corrective retry."""
