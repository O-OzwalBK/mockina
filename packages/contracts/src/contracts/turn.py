from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from contracts.common import ImmutableModel
from contracts.evaluation import Evaluation
from contracts.interviewer import Question
from contracts.transcript import Answer

MAX_GRADING_ERROR_LENGTH = 500


class TurnStatus(StrEnum):
    """Where a turn is in its life cycle.

    - awaiting_answer: the question was asked and the user has not answered yet.
    - awaiting_grade: the user answered and the answer is waiting to be graded.
    - graded: the answer was graded and the evaluation is attached.
    - grading_failed: grading did not succeed; grading_error says why, and it can be retried.
    """

    AWAITING_ANSWER = "awaiting_answer"
    AWAITING_GRADE = "awaiting_grade"
    GRADED = "graded"
    GRADING_FAILED = "grading_failed"


# For each status: must (answer, evaluation, grading_error) be present?
EXPECTED_PARTS: dict[TurnStatus, tuple[bool, bool, bool]] = {
    TurnStatus.AWAITING_ANSWER: (False, False, False),
    TurnStatus.AWAITING_GRADE: (True, False, False),
    TurnStatus.GRADED: (True, True, False),
    TurnStatus.GRADING_FAILED: (True, False, True),
}


class Turn(ImmutableModel):
    """One question-and-answer exchange in an interview session.

    A turn moves through the states described by TurnStatus, and the fields that
    must be present depend on the state. A turn is immutable: to move it to its
    next state, call `updated()`, which re-validates the result. Do not use
    `model_copy(update=...)`, because it skips validation and can produce an
    invalid turn.
    """

    question: Question = Field(description="The question the interviewer asked.")
    status: TurnStatus = Field(
        description="Where the turn is in its life cycle.",
        default=TurnStatus.AWAITING_ANSWER,
        examples=["awaiting_answer"],
    )
    answer: Answer | None = Field(
        description="What the user said. Present once the user has answered.",
        default=None,
    )
    evaluation: Evaluation | None = Field(
        description="The grade for the answer. Present only when the status is graded.",
        default=None,
    )
    grading_error: str | None = Field(
        description=(
            "Short, cleaned-up reason that grading failed, not the raw provider error. "
            "Present only when the status is grading_failed."
        ),
        default=None,
        min_length=1,
        max_length=MAX_GRADING_ERROR_LENGTH,
        examples=["The provider timed out."],
    )

    @model_validator(mode="after")
    def check_lifecycle_rules(self) -> Self:
        """Reject turns whose fields do not match their status or their question."""
        actual = (
            self.answer is not None,
            self.evaluation is not None,
            self.grading_error is not None,
        )
        expected = EXPECTED_PARTS[self.status]
        if actual != expected:
            raise ValueError(
                f"A turn with status '{self.status}' must have "
                f"(answer, evaluation, grading_error) present = {expected}, "
                f"but has {actual}."
            )
        if self.evaluation is not None and self.evaluation.question_id != self.question.id:
            raise ValueError(
                "The evaluation grades a different question than this turn's question."
            )
        return self
