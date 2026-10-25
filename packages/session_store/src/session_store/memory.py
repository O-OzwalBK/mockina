"""In-memory implementation of the session store, used by tests and dev routes."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from contracts import (
    Answer,
    Evaluation,
    InterviewSession,
    Preparation,
    PreparationCreate,
    Question,
    SessionStatus,
    SkillGraph,
    Turn,
    TurnStatus,
    utc_now,
)
from contracts.session import MAX_TURNS_PER_SESSION

from session_store.errors import (
    InvalidStateError,
    NotFoundError,
    OpenQuestionError,
    PreparationLockedError,
    SessionFullError,
)
from session_store.models import (
    AwaitingGrade,
    PreparationSummary,
    SessionSummary,
    UserRecord,
)


@dataclass
class _PreparationRow:
    owner_id: UUID
    preparation: Preparation
    skill_graph: SkillGraph | None = None


@dataclass
class _SessionRow:
    owner_id: UUID
    session: InterviewSession


class InMemorySessionStore:
    """A store held in dictionaries for tests and local developer use.

    One asyncio lock serializes every operation, matching SQLite's single writer and
    making a concurrent add-question test meaningful.
    """

    def __init__(self, *, clock: Callable[[], datetime] = utc_now) -> None:
        """Create an empty store with an injectable clock for deterministic tests."""
        self._clock = clock
        self._lock = asyncio.Lock()
        self._users: dict[UUID, UserRecord] = {}
        self._users_by_token: dict[str, UUID] = {}
        self._preparations: dict[UUID, _PreparationRow] = {}
        self._sessions: dict[UUID, _SessionRow] = {}

    def _now(self) -> datetime:
        """The current UTC time from the injected clock."""
        return self._clock().astimezone(UTC)

    def _preparation(self, user_id: UUID, preparation_id: UUID) -> _PreparationRow:
        """Return an owned preparation or raise NotFoundError."""
        row = self._preparations.get(preparation_id)
        if row is None or row.owner_id != user_id:
            raise NotFoundError("The preparation was not found.")
        return row

    def _session(self, user_id: UUID, session_id: UUID) -> _SessionRow:
        """Return an owned session or raise NotFoundError."""
        row = self._sessions.get(session_id)
        if row is None or row.owner_id != user_id:
            raise NotFoundError("The session was not found.")
        return row

    def _summary(self, session: InterviewSession) -> SessionSummary:
        """Build the counts the API needs for one session."""
        return SessionSummary(
            id=session.id,
            preparation_id=session.preparation_id,
            status=session.status,
            started_at=session.started_at,
            ended_at=session.ended_at,
            turns_total=len(session.turns),
            turns_graded=sum(turn.status == TurnStatus.GRADED for turn in session.turns),
        )

    async def create_user(self, token_hash: str) -> UserRecord:
        """Create an anonymous user with the given token hash."""
        async with self._lock:
            if token_hash in self._users_by_token:
                raise ValueError("This token is already registered.")
            now = self._now()
            user = UserRecord(
                id=uuid4(),
                token_hash=token_hash,
                created_at=now,
                last_seen_at=now,
            )
            self._users[user.id] = user
            self._users_by_token[token_hash] = user.id
            return user

    async def get_user_by_token_hash(self, token_hash: str) -> UserRecord | None:
        """Find a user by the hash of its bearer token."""
        async with self._lock:
            user_id = self._users_by_token.get(token_hash)
            return self._users.get(user_id) if user_id is not None else None

    async def touch_user(self, user_id: UUID) -> None:
        """Update last_seen_at, at most once per UTC day."""
        async with self._lock:
            user = self._users.get(user_id)
            if user is None:
                raise NotFoundError("The user was not found.")
            now = self._now()
            if now - user.last_seen_at < timedelta(days=1):
                return
            self._users[user_id] = UserRecord(
                id=user.id,
                token_hash=user.token_hash,
                created_at=user.created_at,
                last_seen_at=now,
            )

    async def delete_user(self, user_id: UUID) -> None:
        """Delete the user and every row that belongs to them."""
        async with self._lock:
            user = self._users.pop(user_id, None)
            if user is None:
                raise NotFoundError("The user was not found.")
            self._users_by_token.pop(user.token_hash, None)
            preparation_ids = {
                preparation_id
                for preparation_id, row in self._preparations.items()
                if row.owner_id == user_id
            }
            for preparation_id in preparation_ids:
                self._preparations.pop(preparation_id, None)
            for session_id, row in list(self._sessions.items()):
                if row.owner_id == user_id or row.session.preparation_id in preparation_ids:
                    self._sessions.pop(session_id, None)

    async def purge_users(self, inactive_since: datetime) -> int:
        """Delete users whose last_seen_at is before the cutoff."""
        async with self._lock:
            user_ids = [
                user_id
                for user_id, user in self._users.items()
                if user.last_seen_at < inactive_since
            ]
        for user_id in user_ids:
            await self.delete_user(user_id)
        return len(user_ids)

    async def create_preparation(self, user_id: UUID, data: PreparationCreate) -> Preparation:
        """Create a preparation owned by the user."""
        async with self._lock:
            if user_id not in self._users:
                raise NotFoundError("The user was not found.")
            preparation = Preparation(
                id=uuid4(),
                created_at=self._now(),
                **data.model_dump(),
            )
            self._preparations[preparation.id] = _PreparationRow(
                owner_id=user_id,
                preparation=preparation,
            )
            return preparation

    async def get_preparation(self, user_id: UUID, preparation_id: UUID) -> Preparation | None:
        """Read one preparation owned by the user, or None."""
        async with self._lock:
            row = self._preparations.get(preparation_id)
            if row is None or row.owner_id != user_id:
                return None
            return row.preparation

    async def list_preparations(self, user_id: UUID) -> tuple[PreparationSummary, ...]:
        """List the user's preparations newest first."""
        async with self._lock:
            summaries = []
            for row in self._preparations.values():
                if row.owner_id != user_id:
                    continue
                sessions = [
                    session
                    for session_row in self._sessions.values()
                    if session_row.owner_id == user_id
                    and (session := session_row.session).preparation_id == row.preparation.id
                ]
                summaries.append(
                    PreparationSummary(
                        id=row.preparation.id,
                        job_title=row.preparation.job_title,
                        created_at=row.preparation.created_at,
                        session_count=len(sessions),
                        last_session_at=max(
                            (session.updated_at for session in sessions), default=None
                        ),
                    )
                )
            return tuple(sorted(summaries, key=lambda item: item.created_at, reverse=True))

    async def update_preparation(
        self,
        user_id: UUID,
        preparation_id: UUID,
        *,
        job_title: str,
        job_description: str,
        resume: str | None,
    ) -> Preparation:
        """Edit text only while the preparation has no sessions.

        The skill graph is cleared only when the title or the description changed,
        because those are the only texts skill extraction reads.
        """
        async with self._lock:
            row = self._preparation(user_id, preparation_id)
            if any(
                session_row.session.preparation_id == preparation_id
                and session_row.owner_id == user_id
                for session_row in self._sessions.values()
            ):
                raise PreparationLockedError(
                    "A preparation with a session can no longer be edited."
                )
            updated = row.preparation.updated(
                job_title=job_title,
                job_description=job_description,
                resume=resume,
            )
            extraction_inputs_changed = (
                updated.job_title != row.preparation.job_title
                or updated.job_description != row.preparation.job_description
            )
            self._preparations[preparation_id] = _PreparationRow(
                owner_id=user_id,
                preparation=updated,
                skill_graph=None if extraction_inputs_changed else row.skill_graph,
            )
            return updated

    async def delete_preparation(self, user_id: UUID, preparation_id: UUID) -> None:
        """Delete a preparation, its graph and its sessions."""
        async with self._lock:
            self._preparation(user_id, preparation_id)
            self._preparations.pop(preparation_id, None)
            for session_id, row in list(self._sessions.items()):
                if row.session.preparation_id == preparation_id:
                    self._sessions.pop(session_id, None)

    async def get_skill_graph(self, user_id: UUID, preparation_id: UUID) -> SkillGraph | None:
        """Read the preparation's saved graph, or None."""
        async with self._lock:
            return self._preparation(user_id, preparation_id).skill_graph

    async def save_skill_graph_if_absent(
        self, user_id: UUID, preparation_id: UUID, graph: SkillGraph
    ) -> SkillGraph:
        """Save the first graph for a preparation; return the stored one."""
        async with self._lock:
            row = self._preparation(user_id, preparation_id)
            if row.skill_graph is not None:
                return row.skill_graph
            row.skill_graph = graph
            return graph

    async def create_session(self, user_id: UUID, preparation_id: UUID) -> InterviewSession:
        """Start an empty in-progress session."""
        async with self._lock:
            self._preparation(user_id, preparation_id)
            now = self._now()
            session = InterviewSession(
                id=uuid4(),
                preparation_id=preparation_id,
                started_at=now,
                updated_at=now,
            )
            self._sessions[session.id] = _SessionRow(owner_id=user_id, session=session)
            return session

    async def get_session(self, user_id: UUID, session_id: UUID) -> InterviewSession | None:
        """Read one session with all turns, or None."""
        async with self._lock:
            row = self._sessions.get(session_id)
            if row is None or row.owner_id != user_id:
                return None
            return row.session

    async def list_sessions(
        self, user_id: UUID, preparation_id: UUID
    ) -> tuple[SessionSummary, ...]:
        """List the preparation's sessions newest first."""
        async with self._lock:
            self._preparation(user_id, preparation_id)
            summaries = [
                self._summary(row.session)
                for row in self._sessions.values()
                if row.owner_id == user_id and row.session.preparation_id == preparation_id
            ]
            return tuple(sorted(summaries, key=lambda item: item.started_at, reverse=True))

    async def add_question(self, user_id: UUID, session_id: UUID, question: Question) -> Turn:
        """Append an open question unless one is open, the cap is reached, or the session is closed."""
        async with self._lock:
            row = self._session(user_id, session_id)
            session = row.session
            if session.status != SessionStatus.IN_PROGRESS:
                raise InvalidStateError("The session is not in progress.")
            if session.turns and session.turns[-1].status == TurnStatus.AWAITING_ANSWER:
                raise OpenQuestionError(session.turns[-1])
            if len(session.turns) >= MAX_TURNS_PER_SESSION:
                raise SessionFullError("The session already has the maximum number of turns.")
            turn = Turn(question=question)
            row.session = session.updated(
                turns=(*session.turns, turn),
                updated_at=self._now(),
            )
            return turn

    async def get_open_turn(self, user_id: UUID, session_id: UUID) -> Turn | None:
        """Return the last turn when it still awaits an answer."""
        async with self._lock:
            session = self._session(user_id, session_id).session
            if session.turns and session.turns[-1].status == TurnStatus.AWAITING_ANSWER:
                return session.turns[-1]
            return None

    def _turn_index(self, session: InterviewSession, question_id: UUID) -> int:
        """Find a turn by question id or raise NotFoundError."""
        for index, turn in enumerate(session.turns):
            if turn.question.id == question_id:
                return index
        raise NotFoundError("The turn was not found.")

    async def record_answer(
        self, user_id: UUID, session_id: UUID, question_id: UUID, answer: Answer
    ) -> Turn:
        """Store an answer idempotently; a different body is invalid."""
        async with self._lock:
            row = self._session(user_id, session_id)
            session = row.session
            index = self._turn_index(session, question_id)
            turn = session.turns[index]
            if turn.answer is not None:
                if turn.answer == answer:
                    return turn
                raise InvalidStateError("This question has already been answered.")
            if session.status != SessionStatus.IN_PROGRESS:
                raise InvalidStateError("The session is not in progress.")
            updated_turn = turn.updated(status=TurnStatus.AWAITING_GRADE, answer=answer)
            turns = list(session.turns)
            turns[index] = updated_turn
            row.session = session.updated(turns=tuple(turns), updated_at=self._now())
            return updated_turn

    async def record_evaluation(
        self, user_id: UUID, session_id: UUID, question_id: UUID, evaluation: Evaluation
    ) -> Turn:
        """Move an awaiting-grade turn to graded."""
        async with self._lock:
            row = self._session(user_id, session_id)
            session = row.session
            index = self._turn_index(session, question_id)
            turn = session.turns[index]
            if turn.status != TurnStatus.AWAITING_GRADE:
                raise InvalidStateError("The turn is not awaiting a grade.")
            if evaluation.question_id != question_id:
                raise InvalidStateError("The evaluation belongs to a different question.")
            updated_turn = turn.updated(status=TurnStatus.GRADED, evaluation=evaluation)
            turns = list(session.turns)
            turns[index] = updated_turn
            row.session = session.updated(turns=tuple(turns), updated_at=self._now())
            return updated_turn

    async def record_grading_failure(
        self, user_id: UUID, session_id: UUID, question_id: UUID, message: str
    ) -> Turn:
        """Move an awaiting-grade turn to grading_failed with a short message."""
        async with self._lock:
            row = self._session(user_id, session_id)
            session = row.session
            index = self._turn_index(session, question_id)
            turn = session.turns[index]
            if turn.status != TurnStatus.AWAITING_GRADE:
                raise InvalidStateError("The turn is not awaiting a grade.")
            updated_turn = turn.updated(
                status=TurnStatus.GRADING_FAILED,
                grading_error=message,
            )
            turns = list(session.turns)
            turns[index] = updated_turn
            row.session = session.updated(turns=tuple(turns), updated_at=self._now())
            return updated_turn

    async def reset_for_regrade(self, user_id: UUID, session_id: UUID, question_id: UUID) -> Turn:
        """Move a grading_failed turn back to awaiting_grade."""
        async with self._lock:
            row = self._session(user_id, session_id)
            session = row.session
            index = self._turn_index(session, question_id)
            turn = session.turns[index]
            if turn.status != TurnStatus.GRADING_FAILED:
                raise InvalidStateError("Only a failed grade can be retried.")
            updated_turn = turn.updated(
                status=TurnStatus.AWAITING_GRADE,
                grading_error=None,
            )
            turns = list(session.turns)
            turns[index] = updated_turn
            row.session = session.updated(turns=tuple(turns), updated_at=self._now())
            return updated_turn

    async def list_awaiting_grade(self) -> tuple[AwaitingGrade, ...]:
        """Every turn awaiting grading, across all users, in session order."""
        async with self._lock:
            pending: list[tuple[datetime, int, AwaitingGrade]] = []
            for row in self._sessions.values():
                for index, turn in enumerate(row.session.turns):
                    if turn.status == TurnStatus.AWAITING_GRADE:
                        pending.append(
                            (
                                row.session.started_at,
                                index,
                                AwaitingGrade(
                                    user_id=row.owner_id,
                                    session_id=row.session.id,
                                    question_id=turn.question.id,
                                ),
                            )
                        )
            return tuple(item[2] for item in sorted(pending, key=lambda item: (item[0], item[1])))

    async def questions_asked(self, user_id: UUID, preparation_id: UUID) -> tuple[Question, ...]:
        """Every question asked in every session of the preparation, in order."""
        async with self._lock:
            self._preparation(user_id, preparation_id)
            sessions = sorted(
                (
                    row.session
                    for row in self._sessions.values()
                    if row.owner_id == user_id and row.session.preparation_id == preparation_id
                ),
                key=lambda session: session.started_at,
            )
            return tuple(turn.question for session in sessions for turn in session.turns)

    async def complete_session(self, user_id: UUID, session_id: UUID) -> SessionSummary:
        """End the session, dropping an unanswered last question."""
        async with self._lock:
            row = self._session(user_id, session_id)
            session = row.session
            if session.status == SessionStatus.COMPLETED:
                return self._summary(session)
            if session.status == SessionStatus.ABANDONED:
                raise InvalidStateError("An abandoned session cannot be completed.")
            turns = list(session.turns)
            if turns and turns[-1].status == TurnStatus.AWAITING_ANSWER:
                turns.pop()
            if not any(turn.answer is not None for turn in turns):
                raise InvalidStateError("The session has no answered question to complete.")
            now = self._now()
            row.session = session.updated(
                turns=tuple(turns),
                status=SessionStatus.COMPLETED,
                ended_at=now,
                updated_at=now,
            )
            return self._summary(row.session)

    async def abandon_session(self, user_id: UUID, session_id: UUID) -> SessionSummary:
        """End the session without requiring an answer."""
        async with self._lock:
            row = self._session(user_id, session_id)
            session = row.session
            if session.status == SessionStatus.COMPLETED:
                raise InvalidStateError("A completed session cannot be abandoned.")
            if session.status == SessionStatus.ABANDONED:
                return self._summary(session)
            now = self._now()
            row.session = session.updated(
                status=SessionStatus.ABANDONED,
                ended_at=now,
                updated_at=now,
            )
            return self._summary(row.session)
