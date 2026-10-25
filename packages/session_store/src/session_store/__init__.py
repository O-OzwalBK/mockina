"""Persistence for users, preparations, sessions, turns, answers and evaluations.

The store knows nothing about HTTP. The API and the grading worker depend on the
`SessionStore` protocol; tests and local dev routes use `InMemorySessionStore`, and
the SQLite implementation will provide the same operations.
"""

from session_store.errors import (
    InvalidStateError,
    NotFoundError,
    OpenQuestionError,
    PreparationLockedError,
    SessionFullError,
    SessionStoreError,
)
from session_store.interface import SessionStore
from session_store.memory import InMemorySessionStore
from session_store.models import (
    AwaitingGrade,
    PreparationSummary,
    SessionSummary,
    UserRecord,
)
from session_store.settings import SessionStoreSettings
from session_store.sqlite import SQLiteSessionStore

__all__ = [
    "AwaitingGrade",
    "InMemorySessionStore",
    "InvalidStateError",
    "NotFoundError",
    "OpenQuestionError",
    "PreparationLockedError",
    "PreparationSummary",
    "SessionFullError",
    "SessionStore",
    "SessionStoreError",
    "SessionStoreSettings",
    "SessionSummary",
    "SQLiteSessionStore",
    "UserRecord",
]
