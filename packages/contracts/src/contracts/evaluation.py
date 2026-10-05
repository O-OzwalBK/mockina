from uuid import UUID

from pydantic import ConfigDict, Field

from contracts.common import ImmutableModel

MAX_FEEDBACK_LENGTH = 1_000
MAX_SUMMARY_LENGTH = 2_000


class MetricScore(ImmutableModel):
    """A score for one grading metric, with the reasoning behind it."""

    # An LLM fills this in, so extra keys are ignored instead of failing the grade.
    model_config = ConfigDict(extra="ignore")

    score: int = Field(
        description="Whole-number score from 0 (very poor) to 10 (excellent).",
        ge=0,
        le=10,
        examples=[7],
    )
    feedback: str = Field(
        description="One or two sentences explaining why this score was given.",
        min_length=1,
        max_length=MAX_FEEDBACK_LENGTH,
        examples=["Correct explanation, but it skips how keys affect reconciliation."],
    )


class Evaluation(ImmutableModel):
    """The grade for one answer, scored on four metrics."""

    # An LLM fills this in, so extra keys are ignored instead of failing the grade.
    model_config = ConfigDict(extra="ignore")

    question_id: UUID = Field(
        description="The id of the question this evaluation grades.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    correctness: MetricScore = Field(
        description="Whether the facts and reasoning in the answer are right."
    )
    depth: MetricScore = Field(
        description="How far the answer goes beyond surface-level knowledge."
    )
    clarity: MetricScore = Field(description="How clearly and logically the answer is structured.")
    relevance: MetricScore = Field(
        description="How well the answer addresses the question and the role."
    )
    summary: str = Field(
        description="Overall feedback on the answer, with the most important improvement.",
        min_length=1,
        max_length=MAX_SUMMARY_LENGTH,
        examples=["Strong fundamentals; next time, mention how keys affect list updates."],
    )
