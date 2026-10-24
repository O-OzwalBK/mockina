"""The engine's instance defaults, read from environment variables.

These are the values used when a user, preparation, or session does not set an end
rule. They are kept out of `contracts`, which holds only the shape and the hard
limits.
"""

from typing import Self

from contracts.interview_config import (
    MAX_ANSWER_TIME_SECONDS,
    MAX_MODEL_DECIDES_MAX_QUESTIONS,
    MAX_MODEL_DECIDES_MIN_QUESTIONS,
    MAX_QUESTION_COUNT,
    MIN_ANSWER_TIME_SECONDS,
    MIN_MODEL_DECIDES_MAX_QUESTIONS,
    MIN_MODEL_DECIDES_MIN_QUESTIONS,
    MIN_QUESTION_COUNT,
)
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineSettings(BaseSettings):
    """The interview defaults used when no closer configuration is given.

    Each field is read from the variable named after it with an `ENGINE_` prefix,
    for example `default_question_count` from `ENGINE_DEFAULT_QUESTION_COUNT`. Real
    environment variables win over a `.env` file. Empty variables count as not set,
    and settings cannot change after they are loaded.
    """

    model_config = SettingsConfigDict(
        env_prefix="ENGINE_",
        # Later files win, so a .env in the current folder beats the one at the repo root.
        env_file=("../../.env", ".env"),
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        str_strip_whitespace=True,
    )

    default_question_count: int = Field(
        default=5,
        ge=MIN_QUESTION_COUNT,
        le=MAX_QUESTION_COUNT,
        description="Default number of questions for a new interview.",
        examples=[5],
    )
    default_answer_time_seconds: int = Field(
        default=900,
        ge=MIN_ANSWER_TIME_SECONDS,
        le=MAX_ANSWER_TIME_SECONDS,
        description="Default total answering time, in seconds, for a new interview.",
        examples=[900],
    )
    default_model_decides_min: int = Field(
        default=3,
        ge=MIN_MODEL_DECIDES_MIN_QUESTIONS,
        le=MAX_MODEL_DECIDES_MIN_QUESTIONS,
        description="Default smallest number of questions before the model may finish.",
        examples=[3],
    )
    default_model_decides_max: int = Field(
        default=12,
        ge=MIN_MODEL_DECIDES_MAX_QUESTIONS,
        le=MAX_MODEL_DECIDES_MAX_QUESTIONS,
        description="Default largest number of questions the model may ask.",
        examples=[12],
    )

    @model_validator(mode="after")
    def check_model_decides_range(self) -> Self:
        """The minimum must be below the maximum, or the default rule cannot be built."""
        if self.default_model_decides_min >= self.default_model_decides_max:
            raise ValueError(
                "default_model_decides_min must be less than default_model_decides_max."
            )
        return self
