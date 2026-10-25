"""SQLite implementation of the session store, owned by one dedicated thread."""

import asyncio
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
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

SCHEMA_VERSION = 1

SCHEMA_V1 = """
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE preparations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_title TEXT NOT NULL,
    job_description TEXT NOT NULL,
    resume TEXT,
    created_at TEXT NOT NULL,
    skill_graph TEXT
);

CREATE INDEX preparations_by_user_created
    ON preparations(user_id, created_at DESC);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    preparation_id TEXT NOT NULL REFERENCES preparations(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX sessions_by_preparation_started
    ON sessions(preparation_id, started_at DESC);

CREATE TABLE turns (
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    question_id TEXT NOT NULL UNIQUE,
    question_text TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    difficulty INTEGER NOT NULL,
    status TEXT NOT NULL,
    answer_json TEXT,
    evaluation_json TEXT,
    grading_error TEXT,
    PRIMARY KEY (session_id, sequence),
    UNIQUE (session_id, sequence)
);

CREATE UNIQUE INDEX one_open_turn
    ON turns(session_id)
    WHERE status = 'awaiting_answer';

CREATE INDEX turns_by_status ON turns(status, session_id, sequence);
"""


def _iso(value: datetime) -> str:
    """Store times as timezone-aware ISO-8601 text in UTC."""
    return value.astimezone(UTC).isoformat()


def _time(value: str) -> datetime:
    """Read an ISO-8601 time back as an aware datetime."""
    return datetime.fromisoformat(value)


def _question_from_row(row: sqlite3.Row) -> Question:
    """Build a Question from its stored columns."""
    return Question(
        id=UUID(row["question_id"]),
        text=row["question_text"],
        skill_id=row["skill_id"],
        difficulty=row["difficulty"],
    )


def _turn_from_row(row: sqlite3.Row) -> Turn:
    """Build a Turn, including its optional answer and evaluation."""
    answer = Answer.model_validate_json(row["answer_json"]) if row["answer_json"] else None
    evaluation = (
        Evaluation.model_validate_json(row["evaluation_json"]) if row["evaluation_json"] else None
    )
    return Turn(
        question=_question_from_row(row),
        status=TurnStatus(row["status"]),
        answer=answer,
        evaluation=evaluation,
        grading_error=row["grading_error"],
    )


class SQLiteSessionStore:
    """A durable store whose connection is used only by one dedicated thread.

    Every write runs in ``BEGIN IMMEDIATE`` on that thread, so ``sqlite3``'s single
    writer is respected. A partial unique index also prevents two open questions.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """Open the database, set its pragmas and apply pending migrations."""
        self._path = str(path)
        self._clock = clock
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="session-store")
        try:
            self._connection = self._executor.submit(self._open).result()
        except BaseException:
            self._executor.shutdown(wait=True)
            raise

    def _open(self) -> sqlite3.Connection:
        """Create the connection and set every required pragma on it."""
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA secure_delete = ON")
        self._migrate(connection)
        return connection

    def _migrate(self, connection: sqlite3.Connection) -> None:
        """Apply ordered migrations, tracked by SQLite's user_version."""
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError("This database was created by a newer session store.")
        if version < 1:
            connection.executescript(SCHEMA_V1)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        """Close the connection and stop the owning thread. Safe to call twice."""
        if self._closed:
            return
        self._closed = True
        self._executor.submit(self._connection.close).result()
        self._executor.shutdown(wait=True)

    async def _run(self, operation: Callable[[sqlite3.Connection], object]):
        """Run a read or a pragma on the owning thread."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, operation, self._connection)

    async def _write(self, operation: Callable[[sqlite3.Connection], object]):
        """Run one write in BEGIN IMMEDIATE on the owning thread."""

        def run(connection: sqlite3.Connection):
            try:
                connection.execute("BEGIN IMMEDIATE")
                result = operation(connection)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, run, self._connection)

    async def _checkpoint(self) -> None:
        """Move the WAL back into the main file and truncate it."""
        await self._run(lambda connection: connection.execute("PRAGMA wal_checkpoint(TRUNCATE)"))

    def _now(self) -> datetime:
        """The current UTC time from the injected clock."""
        return self._clock().astimezone(UTC)

    def _user_row(self, row: sqlite3.Row) -> UserRecord:
        """Build the user record."""
        return UserRecord(
            id=UUID(row["id"]),
            token_hash=row["token_hash"],
            created_at=_time(row["created_at"]),
            last_seen_at=_time(row["last_seen_at"]),
        )

    def _preparation_from_row(self, row: sqlite3.Row) -> Preparation:
        """Build a Preparation from its stored columns."""
        return Preparation(
            id=UUID(row["id"]),
            created_at=_time(row["created_at"]),
            job_title=row["job_title"],
            job_description=row["job_description"],
            resume=row["resume"],
        )

    def _session_from_row(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> InterviewSession:
        """Build a session with its turns."""
        turns = tuple(
            _turn_from_row(turn_row)
            for turn_row in connection.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY sequence",
                (row["id"],),
            )
        )
        return InterviewSession(
            id=UUID(row["id"]),
            preparation_id=UUID(row["preparation_id"]),
            status=SessionStatus(row["status"]),
            started_at=_time(row["started_at"]),
            ended_at=_time(row["ended_at"]) if row["ended_at"] else None,
            updated_at=_time(row["updated_at"]),
            turns=turns,
        )

    def _session_row(
        self, connection: sqlite3.Connection, user_id: UUID, session_id: UUID
    ) -> sqlite3.Row:
        """Return an owned session row or raise NotFoundError."""
        row = connection.execute(
            "SELECT * FROM sessions WHERE id = ? AND user_id = ?",
            (str(session_id), str(user_id)),
        ).fetchone()
        if row is None:
            raise NotFoundError("The session was not found.")
        return row

    def _preparation_row(
        self, connection: sqlite3.Connection, user_id: UUID, preparation_id: UUID
    ) -> sqlite3.Row:
        """Return an owned preparation row or raise NotFoundError."""
        row = connection.execute(
            "SELECT * FROM preparations WHERE id = ? AND user_id = ?",
            (str(preparation_id), str(user_id)),
        ).fetchone()
        if row is None:
            raise NotFoundError("The preparation was not found.")
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
        now = self._now()
        user_id = uuid4()

        def operation(connection: sqlite3.Connection) -> UserRecord:
            try:
                connection.execute(
                    "INSERT INTO users (id, token_hash, created_at, last_seen_at) "
                    "VALUES (?, ?, ?, ?)",
                    (str(user_id), token_hash, _iso(now), _iso(now)),
                )
            except sqlite3.IntegrityError:
                raise ValueError("This token is already registered.") from None
            return UserRecord(
                id=user_id,
                token_hash=token_hash,
                created_at=now,
                last_seen_at=now,
            )

        return await self._write(operation)

    async def get_user_by_token_hash(self, token_hash: str) -> UserRecord | None:
        """Find a user by the hash of its bearer token."""
        row = await self._run(
            lambda connection: connection.execute(
                "SELECT * FROM users WHERE token_hash = ?", (token_hash,)
            ).fetchone()
        )
        return self._user_row(row) if row is not None else None

    async def touch_user(self, user_id: UUID) -> None:
        """Update last_seen_at, at most once per UTC day."""
        now = self._now()

        def operation(connection: sqlite3.Connection) -> None:
            row = connection.execute("SELECT * FROM users WHERE id = ?", (str(user_id),)).fetchone()
            if row is None:
                raise NotFoundError("The user was not found.")
            user = self._user_row(row)
            if now - user.last_seen_at < timedelta(days=1):
                return
            connection.execute(
                "UPDATE users SET last_seen_at = ? WHERE id = ?",
                (_iso(now), str(user_id)),
            )

        await self._write(operation)

    async def delete_user(self, user_id: UUID) -> None:
        """Delete the user and every row that belongs to them."""

        def operation(connection: sqlite3.Connection) -> None:
            cursor = connection.execute("DELETE FROM users WHERE id = ?", (str(user_id),))
            if cursor.rowcount == 0:
                raise NotFoundError("The user was not found.")

        await self._write(operation)
        await self._checkpoint()

    async def purge_users(self, inactive_since: datetime) -> int:
        """Delete users inactive before the cutoff and return how many."""

        def operation(connection: sqlite3.Connection) -> int:
            rows = connection.execute(
                "SELECT id FROM users WHERE last_seen_at < ?",
                (_iso(inactive_since),),
            ).fetchall()
            connection.executemany("DELETE FROM users WHERE id = ?", [(row["id"],) for row in rows])
            return len(rows)

        deleted = await self._write(operation)
        if deleted:
            await self._checkpoint()
        return deleted

    async def create_preparation(self, user_id: UUID, data: PreparationCreate) -> Preparation:
        """Create a preparation owned by the user."""
        preparation = Preparation(
            id=uuid4(),
            created_at=self._now(),
            **data.model_dump(),
        )

        def operation(connection: sqlite3.Connection) -> Preparation:
            if (
                connection.execute("SELECT 1 FROM users WHERE id = ?", (str(user_id),)).fetchone()
                is None
            ):
                raise NotFoundError("The user was not found.")
            connection.execute(
                "INSERT INTO preparations "
                "(id, user_id, job_title, job_description, resume, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(preparation.id),
                    str(user_id),
                    preparation.job_title,
                    preparation.job_description,
                    preparation.resume,
                    _iso(preparation.created_at),
                ),
            )
            return preparation

        return await self._write(operation)

    async def get_preparation(self, user_id: UUID, preparation_id: UUID) -> Preparation | None:
        """Read one preparation owned by the user, or None."""
        row = await self._run(
            lambda connection: connection.execute(
                "SELECT * FROM preparations WHERE id = ? AND user_id = ?",
                (str(preparation_id), str(user_id)),
            ).fetchone()
        )
        return self._preparation_from_row(row) if row is not None else None

    async def list_preparations(self, user_id: UUID) -> tuple[PreparationSummary, ...]:
        """List the user's preparations newest first."""
        rows = await self._run(
            lambda connection: connection.execute(
                "SELECT p.id, p.job_title, p.created_at, COUNT(s.id) AS session_count, "
                "MAX(s.updated_at) AS last_session_at "
                "FROM preparations p LEFT JOIN sessions s ON s.preparation_id = p.id "
                "WHERE p.user_id = ? GROUP BY p.id ORDER BY p.created_at DESC",
                (str(user_id),),
            ).fetchall()
        )
        return tuple(
            PreparationSummary(
                id=UUID(row["id"]),
                job_title=row["job_title"],
                created_at=_time(row["created_at"]),
                session_count=row["session_count"],
                last_session_at=(_time(row["last_session_at"]) if row["last_session_at"] else None),
            )
            for row in rows
        )

    async def update_preparation(
        self,
        user_id: UUID,
        preparation_id: UUID,
        *,
        job_title: str,
        job_description: str,
        resume: str | None,
    ) -> Preparation:
        """Edit text only while the preparation has no sessions, and clear its graph."""

        def operation(connection: sqlite3.Connection) -> Preparation:
            row = self._preparation_row(connection, user_id, preparation_id)
            if (
                connection.execute(
                    "SELECT 1 FROM sessions WHERE preparation_id = ? LIMIT 1",
                    (str(preparation_id),),
                ).fetchone()
                is not None
            ):
                raise PreparationLockedError(
                    "A preparation with a session can no longer be edited."
                )
            updated = self._preparation_from_row(row).updated(
                job_title=job_title,
                job_description=job_description,
                resume=resume,
            )
            connection.execute(
                "UPDATE preparations SET job_title = ?, job_description = ?, resume = ?, "
                "skill_graph = NULL WHERE id = ?",
                (
                    updated.job_title,
                    updated.job_description,
                    updated.resume,
                    str(preparation_id),
                ),
            )
            return updated

        return await self._write(operation)

    async def delete_preparation(self, user_id: UUID, preparation_id: UUID) -> None:
        """Delete a preparation, its graph and its sessions."""

        def operation(connection: sqlite3.Connection) -> None:
            self._preparation_row(connection, user_id, preparation_id)
            connection.execute("DELETE FROM preparations WHERE id = ?", (str(preparation_id),))

        await self._write(operation)

    async def get_skill_graph(self, user_id: UUID, preparation_id: UUID) -> SkillGraph | None:
        """Read the preparation's saved graph, or None."""
        row = await self._run(
            lambda connection: connection.execute(
                "SELECT skill_graph FROM preparations WHERE id = ? AND user_id = ?",
                (str(preparation_id), str(user_id)),
            ).fetchone()
        )
        if row is None:
            raise NotFoundError("The preparation was not found.")
        return SkillGraph.model_validate_json(row["skill_graph"]) if row["skill_graph"] else None

    async def save_skill_graph_if_absent(
        self, user_id: UUID, preparation_id: UUID, graph: SkillGraph
    ) -> SkillGraph:
        """Save the first graph for a preparation; return the stored one."""

        def operation(connection: sqlite3.Connection) -> SkillGraph:
            self._preparation_row(connection, user_id, preparation_id)
            connection.execute(
                "UPDATE preparations SET skill_graph = ? "
                "WHERE id = ? AND user_id = ? AND skill_graph IS NULL",
                (graph.model_dump_json(), str(preparation_id), str(user_id)),
            )
            row = connection.execute(
                "SELECT skill_graph FROM preparations WHERE id = ?",
                (str(preparation_id),),
            ).fetchone()
            return SkillGraph.model_validate_json(row["skill_graph"])

        return await self._write(operation)

    async def create_session(self, user_id: UUID, preparation_id: UUID) -> InterviewSession:
        """Start an empty in-progress session."""
        now = self._now()
        session = InterviewSession(
            id=uuid4(),
            preparation_id=preparation_id,
            started_at=now,
            updated_at=now,
        )

        def operation(connection: sqlite3.Connection) -> InterviewSession:
            self._preparation_row(connection, user_id, preparation_id)
            connection.execute(
                "INSERT INTO sessions "
                "(id, user_id, preparation_id, status, started_at, ended_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, NULL, ?)",
                (
                    str(session.id),
                    str(user_id),
                    str(preparation_id),
                    session.status.value,
                    _iso(now),
                    _iso(now),
                ),
            )
            return session

        return await self._write(operation)

    async def get_session(self, user_id: UUID, session_id: UUID) -> InterviewSession | None:
        """Read one session with all turns, or None."""
        row = await self._run(
            lambda connection: connection.execute(
                "SELECT * FROM sessions WHERE id = ? AND user_id = ?",
                (str(session_id), str(user_id)),
            ).fetchone()
        )
        if row is None:
            return None
        return await self._run(lambda connection: self._session_from_row(connection, row))

    async def list_sessions(
        self, user_id: UUID, preparation_id: UUID
    ) -> tuple[SessionSummary, ...]:
        """List the preparation's sessions newest first."""
        rows = await self._run(
            lambda connection: connection.execute(
                "SELECT s.*, COUNT(t.question_id) AS turns_total, "
                "COALESCE(SUM(CASE WHEN t.status = 'graded' THEN 1 ELSE 0 END), 0) "
                "AS turns_graded "
                "FROM sessions s LEFT JOIN turns t ON t.session_id = s.id "
                "WHERE s.preparation_id = ? AND s.user_id = ? "
                "GROUP BY s.id ORDER BY s.started_at DESC",
                (str(preparation_id), str(user_id)),
            ).fetchall()
        )
        return tuple(
            SessionSummary(
                id=UUID(row["id"]),
                preparation_id=UUID(row["preparation_id"]),
                status=SessionStatus(row["status"]),
                started_at=_time(row["started_at"]),
                ended_at=_time(row["ended_at"]) if row["ended_at"] else None,
                turns_total=row["turns_total"],
                turns_graded=row["turns_graded"],
            )
            for row in rows
        )

    async def add_question(self, user_id: UUID, session_id: UUID, question: Question) -> Turn:
        """Append an open question unless one is open, the cap is reached, or the session is closed."""

        def operation(connection: sqlite3.Connection) -> Turn:
            row = self._session_row(connection, user_id, session_id)
            if row["status"] != SessionStatus.IN_PROGRESS.value:
                raise InvalidStateError("The session is not in progress.")
            count = connection.execute(
                "SELECT COUNT(*) FROM turns WHERE session_id = ?", (str(session_id),)
            ).fetchone()[0]
            last = connection.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY sequence DESC LIMIT 1",
                (str(session_id),),
            ).fetchone()
            if last is not None and last["status"] == TurnStatus.AWAITING_ANSWER.value:
                raise OpenQuestionError(_turn_from_row(last))
            if count >= MAX_TURNS_PER_SESSION:
                raise SessionFullError("The session already has the maximum number of turns.")
            connection.execute(
                "INSERT INTO turns "
                "(session_id, sequence, question_id, question_text, skill_id, difficulty, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(session_id),
                    count + 1,
                    str(question.id),
                    question.text,
                    question.skill_id,
                    question.difficulty,
                    TurnStatus.AWAITING_ANSWER.value,
                ),
            )
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (_iso(self._now()), str(session_id)),
            )
            return Turn(question=question)

        return await self._write(operation)

    async def get_open_turn(self, user_id: UUID, session_id: UUID) -> Turn | None:
        """Return the last turn when it still awaits an answer."""
        row = await self._run(
            lambda connection: connection.execute(
                "SELECT t.* FROM turns t JOIN sessions s ON s.id = t.session_id "
                "WHERE t.session_id = ? AND s.user_id = ? "
                "ORDER BY t.sequence DESC LIMIT 1",
                (str(session_id), str(user_id)),
            ).fetchone()
        )
        if row is None or row["status"] != TurnStatus.AWAITING_ANSWER.value:
            return None
        return _turn_from_row(row)

    def _answer_row(
        self, connection: sqlite3.Connection, user_id: UUID, session_id: UUID, question_id: UUID
    ) -> sqlite3.Row:
        """Return the session and turn rows for an answer operation."""
        self._session_row(connection, user_id, session_id)
        row = connection.execute(
            "SELECT * FROM turns WHERE session_id = ? AND question_id = ?",
            (str(session_id), str(question_id)),
        ).fetchone()
        if row is None:
            raise NotFoundError("The turn was not found.")
        return row

    async def record_answer(
        self, user_id: UUID, session_id: UUID, question_id: UUID, answer: Answer
    ) -> Turn:
        """Store an answer idempotently; a different body is invalid."""

        def operation(connection: sqlite3.Connection) -> Turn:
            session = self._session_row(connection, user_id, session_id)
            row = self._answer_row(connection, user_id, session_id, question_id)
            if row["answer_json"]:
                stored = Answer.model_validate_json(row["answer_json"])
                if stored == answer:
                    return _turn_from_row(row)
                raise InvalidStateError("This question has already been answered.")
            if session["status"] != SessionStatus.IN_PROGRESS.value:
                raise InvalidStateError("The session is not in progress.")
            connection.execute(
                "UPDATE turns SET status = ?, answer_json = ? "
                "WHERE session_id = ? AND question_id = ?",
                (
                    TurnStatus.AWAITING_GRADE.value,
                    answer.model_dump_json(),
                    str(session_id),
                    str(question_id),
                ),
            )
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (_iso(self._now()), str(session_id)),
            )
            updated = self._answer_row(connection, user_id, session_id, question_id)
            return _turn_from_row(updated)

        return await self._write(operation)

    async def record_evaluation(
        self, user_id: UUID, session_id: UUID, question_id: UUID, evaluation: Evaluation
    ) -> Turn:
        """Move an awaiting-grade turn to graded."""

        def operation(connection: sqlite3.Connection) -> Turn:
            self._session_row(connection, user_id, session_id)
            row = self._answer_row(connection, user_id, session_id, question_id)
            if row["status"] != TurnStatus.AWAITING_GRADE.value:
                raise InvalidStateError("The turn is not awaiting a grade.")
            if evaluation.question_id != question_id:
                raise InvalidStateError("The evaluation belongs to a different question.")
            connection.execute(
                "UPDATE turns SET status = ?, evaluation_json = ?, grading_error = NULL "
                "WHERE session_id = ? AND question_id = ?",
                (
                    TurnStatus.GRADED.value,
                    evaluation.model_dump_json(),
                    str(session_id),
                    str(question_id),
                ),
            )
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (_iso(self._now()), str(session_id)),
            )
            updated = self._answer_row(connection, user_id, session_id, question_id)
            return _turn_from_row(updated)

        return await self._write(operation)

    async def record_grading_failure(
        self, user_id: UUID, session_id: UUID, question_id: UUID, message: str
    ) -> Turn:
        """Move an awaiting-grade turn to grading_failed."""

        def operation(connection: sqlite3.Connection) -> Turn:
            self._session_row(connection, user_id, session_id)
            row = self._answer_row(connection, user_id, session_id, question_id)
            if row["status"] != TurnStatus.AWAITING_GRADE.value:
                raise InvalidStateError("The turn is not awaiting a grade.")
            connection.execute(
                "UPDATE turns SET status = ?, grading_error = ? "
                "WHERE session_id = ? AND question_id = ?",
                (
                    TurnStatus.GRADING_FAILED.value,
                    message,
                    str(session_id),
                    str(question_id),
                ),
            )
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (_iso(self._now()), str(session_id)),
            )
            updated = self._answer_row(connection, user_id, session_id, question_id)
            return _turn_from_row(updated)

        return await self._write(operation)

    async def reset_for_regrade(self, user_id: UUID, session_id: UUID, question_id: UUID) -> Turn:
        """Move a grading_failed turn back to awaiting_grade."""

        def operation(connection: sqlite3.Connection) -> Turn:
            self._session_row(connection, user_id, session_id)
            row = self._answer_row(connection, user_id, session_id, question_id)
            if row["status"] != TurnStatus.GRADING_FAILED.value:
                raise InvalidStateError("Only a failed grade can be retried.")
            connection.execute(
                "UPDATE turns SET status = ?, grading_error = NULL "
                "WHERE session_id = ? AND question_id = ?",
                (
                    TurnStatus.AWAITING_GRADE.value,
                    str(session_id),
                    str(question_id),
                ),
            )
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (_iso(self._now()), str(session_id)),
            )
            updated = self._answer_row(connection, user_id, session_id, question_id)
            return _turn_from_row(updated)

        return await self._write(operation)

    async def list_awaiting_grade(self) -> tuple[AwaitingGrade, ...]:
        """Every turn awaiting grading, across all users, in session order."""
        rows = await self._run(
            lambda connection: connection.execute(
                "SELECT s.user_id, t.session_id, t.question_id "
                "FROM turns t JOIN sessions s ON s.id = t.session_id "
                "WHERE t.status = ? ORDER BY s.started_at, t.sequence",
                (TurnStatus.AWAITING_GRADE.value,),
            ).fetchall()
        )
        return tuple(
            AwaitingGrade(
                user_id=UUID(row["user_id"]),
                session_id=UUID(row["session_id"]),
                question_id=UUID(row["question_id"]),
            )
            for row in rows
        )

    async def questions_asked(self, user_id: UUID, preparation_id: UUID) -> tuple[Question, ...]:
        """Every question asked in every session of the preparation, in order."""
        rows = await self._run(
            lambda connection: connection.execute(
                "SELECT t.* FROM turns t JOIN sessions s ON s.id = t.session_id "
                "WHERE s.user_id = ? AND s.preparation_id = ? "
                "ORDER BY s.started_at, t.sequence",
                (str(user_id), str(preparation_id)),
            ).fetchall()
        )
        return tuple(_question_from_row(row) for row in rows)

    async def complete_session(self, user_id: UUID, session_id: UUID) -> SessionSummary:
        """End the session, dropping an unanswered last question."""
        now = self._now()

        def operation(connection: sqlite3.Connection) -> SessionSummary:
            row = self._session_row(connection, user_id, session_id)
            session = self._session_from_row(connection, row)
            if session.status == SessionStatus.COMPLETED:
                return self._summary(session)
            if session.status == SessionStatus.ABANDONED:
                raise InvalidStateError("An abandoned session cannot be completed.")
            turns = list(session.turns)
            if turns and turns[-1].status == TurnStatus.AWAITING_ANSWER:
                open_question_id = turns[-1].question.id
                turns.pop()
                connection.execute(
                    "DELETE FROM turns WHERE session_id = ? AND question_id = ?",
                    (str(session_id), str(open_question_id)),
                )
            if not any(turn.answer is not None for turn in turns):
                raise InvalidStateError("The session has no answered question to complete.")
            connection.execute(
                "UPDATE sessions SET status = ?, ended_at = ?, updated_at = ? WHERE id = ?",
                (
                    SessionStatus.COMPLETED.value,
                    _iso(now),
                    _iso(now),
                    str(session_id),
                ),
            )
            completed = self._session_from_row(
                connection, self._session_row(connection, user_id, session_id)
            )
            return self._summary(completed)

        return await self._write(operation)

    async def abandon_session(self, user_id: UUID, session_id: UUID) -> SessionSummary:
        """End the session without requiring an answer."""
        now = self._now()

        def operation(connection: sqlite3.Connection) -> SessionSummary:
            row = self._session_row(connection, user_id, session_id)
            session = self._session_from_row(connection, row)
            if session.status == SessionStatus.COMPLETED:
                raise InvalidStateError("A completed session cannot be abandoned.")
            if session.status == SessionStatus.ABANDONED:
                return self._summary(session)
            connection.execute(
                "UPDATE sessions SET status = ?, ended_at = ?, updated_at = ? WHERE id = ?",
                (
                    SessionStatus.ABANDONED.value,
                    _iso(now),
                    _iso(now),
                    str(session_id),
                ),
            )
            abandoned = self._session_from_row(
                connection, self._session_row(connection, user_id, session_id)
            )
            return self._summary(abandoned)

        return await self._write(operation)
