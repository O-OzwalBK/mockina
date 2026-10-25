"""Small return values the store gives the API, separate from the shared contracts."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from contracts import SessionStatus


@dataclass(frozen=True)
class UserRecord:
    """An anonymous user and the hash of their bearer token."""

    id: UUID
    token_hash: str
    created_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class PreparationSummary:
    """A preparation row with the counts the list page needs."""

    id: UUID
    job_title: str
    created_at: datetime
    session_count: int
    last_session_at: datetime | None


@dataclass(frozen=True)
class SessionSummary:
    """A session row with its progress counts."""

    id: UUID
    preparation_id: UUID
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None
    turns_total: int
    turns_graded: int


@dataclass(frozen=True)
class AwaitingGrade:
    """A turn the grading worker still has to process."""

    user_id: UUID
    session_id: UUID
    question_id: UUID
