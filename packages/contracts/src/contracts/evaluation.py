from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MetricScore(BaseModel):
    """A score for one grading metric, with the reasoning behind it."""

    model_config = ConfigDict(str_strip_whitespace=True)

    score: int = Field(
        ge=0,
        le=10,
        description="Whole-number score from 0 (very poor) to 10 (excellent).",
        examples=[7],
    )
    feedback: str = Field(
        min_length=1,
        description="One or two sentences explaining why this score was given.",
        examples=["Correct explanation, but it skips how keys affect reconciliation."],
    )


class Evaluation(BaseModel):
    """The grade for one answer, scored on four metrics."""

    model_config = ConfigDict(str_strip_whitespace=True)

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
    clarity: MetricScore = Field(
        description="How clearly and logically the answer is structured."
    )
    relevance: MetricScore = Field(
        description="How well the answer addresses the question and the role."
    )
    summary: str = Field(
        min_length=1,
        description="Overall feedback on the answer, with the most important improvement.",
        examples=["Strong fundamentals; next time, mention how keys affect list updates."],
    )