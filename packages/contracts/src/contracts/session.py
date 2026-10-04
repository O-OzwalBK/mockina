from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from contracts.common import ImmutableModel, UtcDatetime, utc_now
from contracts.turn import Turn, TurnStatus

MAX_TURNS_PER_SESSION = 100

class SessionStatus(StrEnum):
    """Where an interview session is in its life cycle.

    - in_progress: the interview is under way and has no end time.
    - completed: the interview ended. Grading may still be pending or may have failed.
    - abandoned: the user left before finishing.
    """

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class InterviewSession(ImmutableModel):
    """One practice attempt at an interview: an ordered list of turns.

    Many sessions can belong to the same preparation. The session is immutable:
    to add a turn or change its status, call `updated()`, for example
    `session.updated(turns=session.turns + (new_turn,))`.
    """

    id: UUID = Field(
        description="Globally unique identifier of the session, generated when it is created.",
        default_factory=uuid4,
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    preparation_id: UUID = Field(
        description="The id of the preparation (job description and resume) this session practices.",
        examples=["9c1d2e3f-4a5b-4c6d-8e7f-0a1b2c3d4e5f"],
    )
    status: SessionStatus = Field(
        description="Where the session is in its life cycle.",
        default=SessionStatus.IN_PROGRESS,
        examples=["in_progress"],
    )
    started_at: UtcDatetime = Field(
        description="When the session started, as a timezone-aware UTC time.",
        default_factory=utc_now,
        examples=["2026-10-04T09:00:00Z"],
    )
    ended_at: UtcDatetime | None = Field(
        description="When the session ended. Present only when the status is completed or abandoned.",
        default=None,
        examples=["2026-10-04T09:30:00Z"],
    )
    updated_at: UtcDatetime = Field(
        description="When the session last changed, used to resume or expire sessions.",
        default_factory=utc_now,
        examples=["2026-10-04T09:12:00Z"],
    )
    turns: tuple[Turn, ...] = Field(
        description="The turns of the interview, in the order the questions were asked.",
        max_length=MAX_TURNS_PER_SESSION,
        default=(),
    )

    @model_validator(mode="after")
    def check_end_time_matches_status(self) -> Self:
        """An in-progress session has no end time; a completed or abandoned one has."""
        if self.status == SessionStatus.IN_PROGRESS and self.ended_at is not None:
            raise ValueError("An in-progress session cannot have an end time.")
        if self.status != SessionStatus.IN_PROGRESS and self.ended_at is None:
            raise ValueError(f"A {self.status} session must have an end time.")
        return self

    @model_validator(mode="after")
    def check_times_do_not_go_backwards(self) -> Self:
        """The end and update times cannot be earlier than the start time, or the update earlier than the end."""
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at cannot be earlier than started_at.")
        if self.updated_at < self.started_at:
            raise ValueError("updated_at cannot be earlier than started_at.")
        if self.ended_at is not None and self.updated_at < self.ended_at:
            raise ValueError("updated_at cannot be earlier than ended_at.")
        return self

    @model_validator(mode="after")
    def check_questions_are_unique(self) -> Self:
        """The same question cannot appear twice in one session."""
        question_ids = [turn.question.id for turn in self.turns]
        if len(set(question_ids)) != len(question_ids):
            raise ValueError("A question appears more than once in this session.")
        return self

    @model_validator(mode="after")
    def check_only_last_turn_is_open(self) -> Self:
        """Only the last turn may still be waiting for an answer."""
        for turn in self.turns[:-1]:
            if turn.status == TurnStatus.AWAITING_ANSWER:
                raise ValueError("Only the last turn can be awaiting an answer.")
        return self

    @model_validator(mode="after")
    def check_completed_session_was_conducted(self) -> Self:
        """A completed session has at least one turn and no unanswered question."""
        if self.status != SessionStatus.COMPLETED:
            return self
        if not self.turns:
            raise ValueError("A completed session must have at least one turn.")
        if self.turns[-1].status == TurnStatus.AWAITING_ANSWER:
            raise ValueError("A completed session cannot end with an unanswered question.")
        return self