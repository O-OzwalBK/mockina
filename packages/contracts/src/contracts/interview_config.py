"""The interview end rule: how a session decides when it has asked enough.

A rule is one of three shapes, chosen by its `rule` field: a fixed number of
questions, a total time spent answering, or a range in which the model decides.
The bounds here are hard limits shared by every layer that builds a
configuration. Instance defaults belong to the engine, not to this shape.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from contracts.common import ImmutableModel
from contracts.session import MAX_TURNS_PER_SESSION

MIN_QUESTION_COUNT = 1
MAX_QUESTION_COUNT = MAX_TURNS_PER_SESSION
MIN_ANSWER_TIME_SECONDS = 60
MAX_ANSWER_TIME_SECONDS = 3_600
MIN_MODEL_DECIDES_MIN_QUESTIONS = 1
MAX_MODEL_DECIDES_MIN_QUESTIONS = 10
MIN_MODEL_DECIDES_MAX_QUESTIONS = 2
MAX_MODEL_DECIDES_MAX_QUESTIONS = 20


class QuestionCountConfig(ImmutableModel):
    """End the interview after a fixed number of questions."""

    rule: Literal["question_count"] = Field(
        default="question_count",
        description="Which end rule this configuration uses.",
        examples=["question_count"],
    )
    count: int = Field(
        description="Number of questions to ask before the interview ends.",
        ge=MIN_QUESTION_COUNT,
        le=MAX_QUESTION_COUNT,
        examples=[5],
    )


class AnswerTimeConfig(ImmutableModel):
    """End the interview once the answers add up to a time limit."""

    rule: Literal["answer_time"] = Field(
        default="answer_time",
        description="Which end rule this configuration uses.",
        examples=["answer_time"],
    )
    max_seconds: int = Field(
        description="Total time spent answering, in seconds, before the interview ends.",
        ge=MIN_ANSWER_TIME_SECONDS,
        le=MAX_ANSWER_TIME_SECONDS,
        examples=[900],
    )


class ModelDecidesConfig(ImmutableModel):
    """The model decides when to finish, between a minimum and a maximum."""

    rule: Literal["model_decides"] = Field(
        default="model_decides",
        description="Which end rule this configuration uses.",
        examples=["model_decides"],
    )
    min_questions: int = Field(
        description="Smallest number of questions before the model may decide to finish.",
        ge=MIN_MODEL_DECIDES_MIN_QUESTIONS,
        le=MAX_MODEL_DECIDES_MIN_QUESTIONS,
        examples=[3],
    )
    max_questions: int = Field(
        description="Largest number of questions the model may ask before code forces a finish.",
        ge=MIN_MODEL_DECIDES_MAX_QUESTIONS,
        le=MAX_MODEL_DECIDES_MAX_QUESTIONS,
        examples=[12],
    )

    @model_validator(mode="after")
    def check_min_is_below_max(self) -> Self:
        """The minimum must be below the maximum, leaving the model a real decision."""
        if self.min_questions >= self.max_questions:
            raise ValueError("min_questions must be less than max_questions.")
        return self


# A rule chosen at runtime by its `rule` field. Use `TypeAdapter(InterviewConfig)`
# to validate or serialise a configuration whose concrete class is not known.
InterviewConfig = Annotated[
    QuestionCountConfig | AnswerTimeConfig | ModelDecidesConfig,
    Field(discriminator="rule"),
]
