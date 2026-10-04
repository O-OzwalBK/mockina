from itertools import pairwise
from typing import Self

from pydantic import Field, model_validator

from contracts.common import ImmutableModel

MAX_WORD_LENGTH = 100
MAX_TRANSCRIPT_LENGTH = 20_000
MAX_WORDS_PER_ANSWER = 5_000
MAX_ANSWER_DURATION_SECONDS = 1_800


class WordTiming(ImmutableModel):
    """One spoken word and when it was said within an answer."""

    word: str = Field(
        description="The spoken word as transcribed by the speech-to-text model.",
        max_length=MAX_WORD_LENGTH,
        examples=["hello"],
    )
    start: float = Field(
        description="Seconds from the start of the answer at which the word begins.",
        ge=0,
        allow_inf_nan=False,
        examples=[0.0, 1.25],
    )
    end: float = Field(
        description="Seconds from the start of the answer at which the word ends. Never earlier than start.",
        ge=0,
        allow_inf_nan=False,
        examples=[0.4, 1.6],
    )

    @model_validator(mode="after")
    def check_end_is_not_before_start(self) -> Self:
        """A word cannot end before it starts."""
        if self.end < self.start:
            raise ValueError("end cannot be earlier than start.")
        return self


class Answer(ImmutableModel):
    """What the user said in response to one interview question."""

    transcript: str = Field(
        description="Full text of the answer. Empty if the user stayed silent.",
        max_length=MAX_TRANSCRIPT_LENGTH,
        examples=["I would use a hash map to count occurrences."],
    )
    words: tuple[WordTiming, ...] = Field(
        description=(
            "Per-word timings in the order the words were spoken, used to compute "
            "pace and pauses. Empty when the speech-to-text source provides none."
        ),
        default=(),
        max_length=MAX_WORDS_PER_ANSWER,
    )
    duration: float = Field(
        description="Total length of the answer in seconds.",
        ge=0,
        le=MAX_ANSWER_DURATION_SECONDS,
        allow_inf_nan=False,
        examples=[12.5],
    )

    @model_validator(mode="after")
    def check_words_are_in_order(self) -> Self:
        """Words must be listed in the order they were spoken, by start time."""
        for previous, current in pairwise(self.words):
            if current.start < previous.start:
                raise ValueError("Words must be in the order they were spoken.")
        return self