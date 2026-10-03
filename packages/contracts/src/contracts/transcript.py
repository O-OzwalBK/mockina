from pydantic import BaseModel, Field, model_validator


class WordTiming(BaseModel):
    """One spoken word and when it was said within an answer."""

    word: str = Field(
        description="The spoken word as transcribed by the speech-to-text model.",
        examples=["hello"],
    )
    start: float = Field(
        ge=0.0,
        description="Seconds from the start of the answer at which the word begins.",
        examples=[0.0, 1.25],
    )
    end: float = Field(
        ge=0,
        description="Seconds from the start of the answer at which the word ends.",
        examples=[0.4, 1.6],
    )

    @model_validator(mode="after")
    def validate_start_less_than_end(self) -> WordTiming:
        if self.end < self.start:
            raise ValueError(
                f"end timestamp ({self.end}s) must be strictly greater than start timestamp ({self.start}s)"
            )
        return self


class Answer(BaseModel):
    """What the user said in response to one interview question."""

    transcript: str = Field(
        description="Full text of the answer. Empty if the user stayed silent.",
        examples=["I would use a hash map to count occurrences."],
    )
    words: list[WordTiming] = Field(
        default_factory=list,
        description=(
            "Per-word timings, used to compute pace and pauses. "
            "Empty when the speech-to-text source provides none."
        ),
    )
    duration: float = Field(
        ge=0,
        description="Total length of the answer in seconds.",
        examples=[12.5],
    )