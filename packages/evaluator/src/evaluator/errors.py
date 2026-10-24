"""The evaluator's own failure: the model could not produce a usable evaluation."""

from typing import ClassVar

from llm_gateway import LLMError


class EvaluationError(LLMError):
    """The model did not produce a usable evaluation after one corrective retry.

    The failed checks are carried as names, so this error never repeats the answer,
    the prompt, or the job title. The API maps it to a retryable-free bad response;
    a failed grade is retried through the product's regrade path, not automatically.
    """

    retryable: ClassVar[bool] = False

    def __init__(
        self,
        message: str,
        *,
        failures: tuple[str, ...],
        attempts: int,
    ) -> None:
        """Record the failed checks and how many grading calls were tried."""
        super().__init__(message)
        self.failures = failures
        """Names of the checks the model's reply failed."""

        self.attempts = attempts
        """How many grading calls were tried, including the corrective retry."""
