from datetime import UTC, datetime, timedelta

import pytest
from session_store import InMemorySessionStore, SessionStore, SQLiteSessionStore


class MutableClock:
    """A clock the test can move forward by hand."""

    def __init__(self) -> None:
        self.current = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **changes: float) -> None:
        self.current += timedelta(**changes)


@pytest.fixture
def anyio_backend():
    """Run asynchronous store tests on asyncio only."""
    return "asyncio"


@pytest.fixture
def clock() -> MutableClock:
    """A deterministic clock for every store test."""
    return MutableClock()


@pytest.fixture(params=["memory", "sqlite"])
def store(request, clock: MutableClock, tmp_path) -> SessionStore:
    """Run every shared test against both implementations."""
    if request.param == "memory":
        yield InMemorySessionStore(clock=clock)
        return
    sqlite_store = SQLiteSessionStore(tmp_path / "session-store.db", clock=clock)
    try:
        yield sqlite_store
    finally:
        sqlite_store.close()
