"""Request and response shapes that belong to the product API only.

Shapes shared with the browser and the other packages (Preparation, Turn, ...) live in
the `contracts` package. Shapes here exist only on the HTTP boundary.
"""

from uuid import UUID

from contracts import UtcDatetime
from contracts.preparation import (
    MAX_JOB_DESCRIPTION_LENGTH,
    MAX_JOB_TITLE_LENGTH,
    MAX_RESUME_LENGTH,
)
from contracts.transcript import (
    MAX_ANSWER_DURATION_SECONDS,
    MAX_TRANSCRIPT_LENGTH,
    MAX_WORD_LENGTH,
    MAX_WORDS_PER_ANSWER,
)
from pydantic import BaseModel, Field


class Identity(BaseModel):
    """A new anonymous identity. The token is shown here once and the server never stores it."""

    user_id: UUID = Field(
        description="Identifier of the new anonymous user.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    token: str = Field(
        description=(
            "Opaque secret that proves who is calling. Send it as `Authorization: Bearer <token>`. "
            "It cannot be shown again: the server keeps only its SHA-256 hash."
        ),
        examples=["Zm9vYmFyLXRva2VuLWV4YW1wbGUtMDEyMzQ1Njc4OWFi"],
    )
    created_at: UtcDatetime = Field(
        description="When the identity was created, as a timezone-aware UTC time.",
        examples=["2026-10-25T09:30:00Z"],
    )


class Limits(BaseModel):
    """Size limits the server enforces, so the browser can check input before sending it.

    Every value comes from a constant in the `contracts` package, so the browser and the
    server cannot disagree.
    """

    max_job_title_length: int = Field(
        description="Longest job title, in characters.", examples=[MAX_JOB_TITLE_LENGTH]
    )
    max_job_description_length: int = Field(
        description="Longest job description, in characters.",
        examples=[MAX_JOB_DESCRIPTION_LENGTH],
    )
    max_resume_length: int = Field(
        description="Longest resume text, in characters.", examples=[MAX_RESUME_LENGTH]
    )
    max_transcript_length: int = Field(
        description="Longest answer transcript, in characters.",
        examples=[MAX_TRANSCRIPT_LENGTH],
    )
    max_words_per_answer: int = Field(
        description="Most word timings one answer may carry.", examples=[MAX_WORDS_PER_ANSWER]
    )
    max_word_length: int = Field(
        description="Longest single word in an answer, in characters.",
        examples=[MAX_WORD_LENGTH],
    )
    max_answer_seconds: int = Field(
        description="Longest an answer may last, in seconds.",
        examples=[MAX_ANSWER_DURATION_SECONDS],
    )


def current_limits() -> Limits:
    """The limits as the contracts define them right now."""
    return Limits(
        max_job_title_length=MAX_JOB_TITLE_LENGTH,
        max_job_description_length=MAX_JOB_DESCRIPTION_LENGTH,
        max_resume_length=MAX_RESUME_LENGTH,
        max_transcript_length=MAX_TRANSCRIPT_LENGTH,
        max_words_per_answer=MAX_WORDS_PER_ANSWER,
        max_word_length=MAX_WORD_LENGTH,
        max_answer_seconds=MAX_ANSWER_DURATION_SECONDS,
    )


class Capabilities(BaseModel):
    """What this server offers, readable without an identity."""

    anonymous_retention_days: int = Field(
        description="Days an anonymous user may stay inactive before their data is due for deletion.",
        examples=[30],
    )
    hosted_stt: bool = Field(
        description="Whether this server can transcribe audio itself. Today it cannot.",
        examples=[False],
    )
    dev_routes: bool = Field(
        description="Whether the developer-only model routes are switched on.",
        examples=[False],
    )
    limits: Limits = Field(description="Size limits the server enforces on input.")
