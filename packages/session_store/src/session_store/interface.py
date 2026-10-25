"""The repository interface the API and the grading worker depend on."""

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from contracts import (
    Answer,
    Evaluation,
    InterviewSession,
    Preparation,
    PreparationCreate,
    Question,
    SkillGraph,
    Turn,
)

from session_store.models import (
    AwaitingGrade,
    PreparationSummary,
    SessionSummary,
    UserRecord,
)


@runtime_checkable
class SessionStore(Protocol):
    """Persistence for users, preparations, sessions, turns, answers and evaluations.

    Every operation is scoped by ``user_id``. A preparation or session owned by
    somebody else behaves exactly like a missing one.
    """

    async def create_user(self, token_hash: str) -> UserRecord:
        """Create an anonymous user and return it."""
        ...

    async def get_user_by_token_hash(self, token_hash: str) -> UserRecord | None:
        """Find the user whose hashed token matches, or None."""
        ...

    async def touch_user(self, user_id: UUID) -> None:
        """Update last_seen_at, at most once per UTC day."""
        ...

    async def delete_user(self, user_id: UUID) -> None:
        """Delete the user, every preparation, session, turn, answer and evaluation."""
        ...

    async def purge_users(self, inactive_since: datetime) -> int:
        """Delete users whose last_seen_at is before the cutoff and return how many."""
        ...

    async def create_preparation(self, user_id: UUID, data: PreparationCreate) -> Preparation:
        """Create a preparation owned by the user."""
        ...

    async def get_preparation(self, user_id: UUID, preparation_id: UUID) -> Preparation | None:
        """Read one preparation owned by the user, or None."""
        ...

    async def list_preparations(self, user_id: UUID) -> tuple[PreparationSummary, ...]:
        """List the user's preparations newest first."""
        ...

    async def update_preparation(
        self,
        user_id: UUID,
        preparation_id: UUID,
        *,
        job_title: str,
        job_description: str,
        resume: str | None,
    ) -> Preparation:
        """Replace editable text while the preparation has no sessions, and clear its skill graph."""
        ...

    async def delete_preparation(self, user_id: UUID, preparation_id: UUID) -> None:
        """Delete a preparation, its sessions and its skill graph."""
        ...

    async def get_skill_graph(self, user_id: UUID, preparation_id: UUID) -> SkillGraph | None:
        """Read the preparation's saved skill graph, or None."""
        ...

    async def save_skill_graph_if_absent(
        self, user_id: UUID, preparation_id: UUID, graph: SkillGraph
    ) -> SkillGraph:
        """Save the graph only if none is stored; return the stored graph either way."""
        ...

    async def create_session(self, user_id: UUID, preparation_id: UUID) -> InterviewSession:
        """Start an empty in-progress session for the preparation."""
        ...

    async def get_session(self, user_id: UUID, session_id: UUID) -> InterviewSession | None:
        """Read one session with all its turns, or None."""
        ...

    async def list_sessions(
        self, user_id: UUID, preparation_id: UUID
    ) -> tuple[SessionSummary, ...]:
        """List the preparation's sessions newest first."""
        ...

    async def add_question(self, user_id: UUID, session_id: UUID, question: Question) -> Turn:
        """Append an open question; reject an open question or a full or closed session."""
        ...

    async def get_open_turn(self, user_id: UUID, session_id: UUID) -> Turn | None:
        """Return the last turn when it still awaits an answer, or None."""
        ...

    async def record_answer(
        self, user_id: UUID, session_id: UUID, question_id: UUID, answer: Answer
    ) -> Turn:
        """Store an answer; the same body is idempotent, a different one is invalid."""
        ...

    async def record_evaluation(
        self, user_id: UUID, session_id: UUID, question_id: UUID, evaluation: Evaluation
    ) -> Turn:
        """Move an awaiting-grade turn to graded with its evaluation."""
        ...

    async def record_grading_failure(
        self, user_id: UUID, session_id: UUID, question_id: UUID, message: str
    ) -> Turn:
        """Move an awaiting-grade turn to grading_failed with a short safe message."""
        ...

    async def reset_for_regrade(self, user_id: UUID, session_id: UUID, question_id: UUID) -> Turn:
        """Move a grading_failed turn back to awaiting_grade."""
        ...

    async def list_awaiting_grade(self) -> tuple[AwaitingGrade, ...]:
        """Every turn awaiting grading, across all users, for worker startup."""
        ...

    async def questions_asked(self, user_id: UUID, preparation_id: UUID) -> tuple[Question, ...]:
        """Every question asked in every session of the preparation, in order."""
        ...

    async def complete_session(self, user_id: UUID, session_id: UUID) -> SessionSummary:
        """End the session, dropping an unanswered last question."""
        ...

    async def abandon_session(self, user_id: UUID, session_id: UUID) -> SessionSummary:
        """End the session without requiring an answer."""
        ...
