"""Test setup shared by every API test file."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from api.main import create_app
from api.settings import ApiSettings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from llm_gateway.testing import FakeLLM
from session_store import InMemorySessionStore
from skill_graph import InMemorySkillStore


@pytest.fixture(autouse=True)
def temporary_session_store_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point SESSION_STORE_PATH at a temporary file so no test touches the real data folder.

    The API opens a SQLite database when it starts, unless a test passes its own store.
    Without this fixture every test that starts the app would create `data/` next to
    wherever pytest runs. The folder `data/` inside the temporary directory does not exist
    yet on purpose: it lets a test check that the API creates a missing parent folder.
    """
    path = tmp_path / "data" / "session-store.sqlite3"
    monkeypatch.setenv("SESSION_STORE_PATH", str(path))
    return path


class MutableClock:
    """A clock the test can move forward by hand, so no test waits for real time."""

    def __init__(self) -> None:
        """Start at a fixed moment."""
        self.current = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        """Return the current fake time."""
        return self.current

    def advance(self, **changes: float) -> None:
        """Move the clock forward, for example ``advance(days=2)``."""
        self.current += timedelta(**changes)


@dataclass(frozen=True)
class Credentials:
    """An identity minted through the API: who it is and how to authenticate as it."""

    user_id: UUID
    token: str

    @property
    def headers(self) -> dict[str, str]:
        """The Authorization header that makes a request act as this user."""
        return {"Authorization": f"Bearer {self.token}"}


@pytest.fixture
def clock() -> MutableClock:
    """A hand-moved clock shared by the store."""
    return MutableClock()


@pytest.fixture
def llm() -> FakeLLM:
    """A scripted model double. Tests queue replies on it; it records every call."""
    return FakeLLM()


@pytest.fixture
def store(clock: MutableClock) -> InMemorySessionStore:
    """The in-memory session store the API under test uses."""
    return InMemorySessionStore(clock=clock)


@pytest.fixture
def skill_store() -> InMemorySkillStore:
    """The in-memory skill catalog the API under test uses."""
    return InMemorySkillStore()


@pytest.fixture
def api_settings() -> ApiSettings:
    """API settings with no .env file read and developer routes off."""
    return ApiSettings(_env_file=None)  # pyright: ignore[reportCallIssue]


@pytest.fixture
def app(
    api_settings: ApiSettings,
    llm: FakeLLM,
    store: InMemorySessionStore,
    skill_store: InMemorySkillStore,
) -> FastAPI:
    """The API wired to test doubles for the model, the session store and the skill catalog."""
    return create_app(settings=api_settings, llm=llm, skill_store=skill_store, store=store)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A test client with the app started, so lifespan setup and shutdown both run."""
    with TestClient(app) as running:
        yield running


@pytest.fixture
def mint_identity(client: TestClient) -> Callable[[], Credentials]:
    """A function that creates a new anonymous identity through POST /v1/identity."""

    def mint() -> Credentials:
        response = client.post("/v1/identity")
        assert response.status_code == 201
        body = response.json()
        return Credentials(user_id=UUID(body["user_id"]), token=body["token"])

    return mint
