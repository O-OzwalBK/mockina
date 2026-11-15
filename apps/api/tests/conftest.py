"""Test setup shared by every API test file."""

from collections.abc import Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from api.main import create_app
from api.settings import ApiSettings
from contracts import Preparation, Question, Turn
from engine import EngineOutcome
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


@dataclass(frozen=True)
class InterviewerCall:
    """What the routes handed to the question source on one call, kept for the test to check."""

    user_id: UUID
    preparation: Preparation
    turns: tuple[Turn, ...]
    earlier_questions: tuple[Question, ...]


class FakeInterviewer:
    """A question source that plays a script instead of asking a model.

    Give it the outcomes you want, in order. An outcome is a `Question`, an `InterviewFinished`,
    an exception (raised), or an async function with no arguments that returns one of the
    others, which lets a test make the call slow or do something while it is "thinking". Every
    call is recorded in `calls`. A call beyond the script raises AssertionError, so a route that
    asks more often than the test expected cannot go unnoticed.
    """

    def __init__(
        self,
        *script: EngineOutcome | BaseException | Callable[[], Awaitable[EngineOutcome]],
    ) -> None:
        """Remember the outcomes to play back."""
        self._script = list(script)
        self.calls: list[InterviewerCall] = []

    def add(
        self,
        *script: EngineOutcome | BaseException | Callable[[], Awaitable[EngineOutcome]],
    ) -> None:
        """Queue more outcomes after the ones already waiting."""
        self._script.extend(script)

    async def next_question(
        self,
        *,
        user_id: UUID,
        preparation: Preparation,
        turns: Sequence[Turn],
        earlier_questions: Sequence[Question],
    ) -> EngineOutcome:
        """Record the call, then play the next scripted outcome."""
        self.calls.append(
            InterviewerCall(user_id, preparation, tuple(turns), tuple(earlier_questions))
        )
        if not self._script:
            raise AssertionError(
                "The route asked the interviewer more often than the test scripted."
            )
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            return await item()
        return item


@pytest.fixture
def interviewer() -> FakeInterviewer:
    """A scripted question source, empty at first. Tests queue outcomes with `interviewer.add(...)`."""
    return FakeInterviewer()


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
    return ApiSettings(_env_file=None, dev_routes=False)  # pyright: ignore[reportCallIssue]


@pytest.fixture
def app(
    api_settings: ApiSettings,
    llm: FakeLLM,
    store: InMemorySessionStore,
    skill_store: InMemorySkillStore,
    interviewer: FakeInterviewer,
) -> FastAPI:
    """The API wired to test doubles for the model, the stores and the question source."""
    return create_app(
        settings=api_settings,
        llm=llm,
        skill_store=skill_store,
        store=store,
        interviewer=interviewer,
    )


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


@pytest.fixture
def user(mint_identity: Callable[[], Credentials]) -> Credentials:
    """The signed-in user most tests act as."""
    return mint_identity()


@pytest.fixture
def other_user(mint_identity: Callable[[], Credentials], user: Credentials) -> Credentials:
    """A second user, for checking that one user can never reach another's data."""
    return mint_identity()


@pytest.fixture
def product_operations(app: FastAPI) -> list[tuple[str, str, dict]]:
    """Every product operation as (METHOD, path, OpenAPI operation): all /v1 except /v1/dev.

    The list comes from the OpenAPI document rather than from the router objects, because
    that document is the public list of routes and does not depend on how FastAPI stores
    included routers internally. A product route left out of the documentation would not be
    checked, which the project's documentation rule forbids anyway.
    """
    operations = []
    for path, item in app.openapi()["paths"].items():
        if not path.startswith("/v1/") or path.startswith("/v1/dev/"):
            continue
        for method, operation in item.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                operations.append((method.upper(), path, operation))
    return operations


@pytest.fixture
def public_routes() -> set[tuple[str, str]]:
    """The product routes anyone may call without a token. Every other /v1 route needs one.

    Job presets will be added here when they are built. This is the one place that lists them.
    """
    return {("GET", "/v1/capabilities"), ("POST", "/v1/identity")}
