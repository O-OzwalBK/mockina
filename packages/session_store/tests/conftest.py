from datetime import UTC, datetime, timedelta

import pytest
from session_store import InMemorySessionStore


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


@pytest.fixture
def store(clock: MutableClock) -> InMemorySessionStore:
    """A fresh in-memory store with the test clock."""
    return InMemorySessionStore(clock=clock)
