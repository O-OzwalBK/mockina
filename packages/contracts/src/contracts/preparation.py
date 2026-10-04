from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from contracts.common import UtcDatetime, utc_now

MAX_JOB_TITLE_LENGTH = 120
MAX_JOB_DESCRIPTION_LENGTH = 20_000
MAX_RESUME_LENGTH = 20_000


# Client request shape

class PreparationCreate(BaseModel):
    """What a client sends to start preparing for a job."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    job_title: str = Field(
        description="Short name for the target job, shown when listing preparations.",
        min_length=1,
        max_length=MAX_JOB_TITLE_LENGTH,
        examples=["Junior React Developer"],
    )
    job_description: str = Field(
        description="Full text of the job description, pasted by the user or taken from a preset.",
        min_length=1,
        max_length=MAX_JOB_DESCRIPTION_LENGTH,
        examples=["We are looking for a junior developer with React experience."],
    )
    resume: str | None = Field(
        description="Optional resume text. Omit it or send null when there is none.",
        default=None,
        min_length=1,
        max_length=MAX_RESUME_LENGTH,
        examples=["Built a task tracker with React and TypeScript."],
    )


# Server owned fields

class Preparation(PreparationCreate):
    """A stored preparation: what the client sent, plus the fields the server owns."""

    id: UUID = Field(
        description="Globally unique identifier of the preparation, generated when it is created.",
        default_factory=uuid4,
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    created_at: UtcDatetime = Field(
        default_factory=utc_now,
        description="When the preparation was created, as a timezone-aware UTC time.",
        examples=["2026-10-03T09:30:00Z"],
    )