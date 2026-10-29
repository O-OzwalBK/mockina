"""Request and response shapes that belong to the product API only.

Shapes shared with the browser and the other packages (Preparation, Turn, ...) live in
the `contracts` package. Shapes here exist only on the HTTP boundary.
"""

from typing import Self
from uuid import UUID

from contracts import ImmutableModel, SessionStatus, UtcDatetime
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
from pydantic import BaseModel, ConfigDict, Field, model_validator


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
        description=(
            "Days an anonymous user may stay inactive before their data is due for deletion. "
            "0 means the data is kept until the user deletes it."
        ),
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


class PreparationUpdate(ImmutableModel):
    """The fields a client may change on a preparation. Fields left out stay as they are."""

    job_title: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_JOB_TITLE_LENGTH,
        description="New job title. Leave it out to keep the current one; it cannot be null.",
        examples=["Senior React Developer"],
    )
    job_description: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_JOB_DESCRIPTION_LENGTH,
        description="New job description. Leave it out to keep the current one; it cannot be null.",
        examples=["Lead the design of our React component library."],
    )
    resume: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_RESUME_LENGTH,
        description="New resume text. Send null to remove the resume; leave it out to keep it.",
        examples=["Built a task tracker with React and TypeScript."],
    )

    @model_validator(mode="after")
    def check_the_request_changes_something_valid(self) -> Self:
        """Reject an empty body, and a null title or description, which cannot be cleared."""
        sent = self.model_fields_set
        if not sent:
            raise ValueError("Send at least one field to change.")
        for name in ("job_title", "job_description"):
            if name in sent and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class PreparationSummary(BaseModel):
    """A preparation as one row of the home page list, with its session counts."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        description="Identifier of the preparation.",
        examples=["9c1d2e3f-4a5b-4c6d-8e7f-0a1b2c3d4e5f"],
    )
    job_title: str = Field(description="The job title.", examples=["Junior React Developer"])
    created_at: UtcDatetime = Field(
        description="When the preparation was created.", examples=["2026-10-25T09:30:00Z"]
    )
    session_count: int = Field(
        description="How many sessions have been started for this preparation.", examples=[2]
    )
    last_session_at: UtcDatetime | None = Field(
        description="When the newest session started, or null if there is none yet.",
        examples=["2026-10-26T18:00:00Z"],
    )


class PreparationList(BaseModel):
    """The caller's preparations, newest first."""

    items: list[PreparationSummary] = Field(description="One summary per preparation.")


class SessionSummary(BaseModel):
    """A session without its turns: its state and how far grading has come."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        description="Identifier of the session.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    preparation_id: UUID = Field(
        description="The preparation this session practices.",
        examples=["9c1d2e3f-4a5b-4c6d-8e7f-0a1b2c3d4e5f"],
    )
    status: SessionStatus = Field(
        description="Whether the session is in progress, completed or abandoned.",
        examples=["completed"],
    )
    started_at: UtcDatetime = Field(
        description="When the session started.", examples=["2026-10-26T18:00:00Z"]
    )
    ended_at: UtcDatetime | None = Field(
        description="When the session ended, or null while it is in progress.",
        examples=["2026-10-26T18:20:00Z"],
    )
    turns_total: int = Field(description="How many questions the session holds.", examples=[5])
    turns_graded: int = Field(
        description="How many of those answers have a finished grade.", examples=[3]
    )


class SessionList(BaseModel):
    """A preparation's sessions, newest first."""

    items: list[SessionSummary] = Field(description="One summary per session.")
