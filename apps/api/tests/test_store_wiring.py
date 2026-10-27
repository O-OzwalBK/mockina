"""Tests for how the API creates, shares and closes its session store."""

import asyncio
from pathlib import Path

import pytest
from api.dependencies import get_store
from api.main import create_app
from api.settings import ApiSettings
from fastapi import Depends
from fastapi.testclient import TestClient
from llm_gateway.testing import FakeLLM
from session_store import (
    InMemorySessionStore,
    SessionStore,
    SessionStoreSettings,
    SQLiteSessionStore,
)


class SpyStore(InMemorySessionStore):
    """An in-memory store that counts close() calls, to see who closes what."""

    def __init__(self) -> None:
        """Start with no close calls recorded."""
        super().__init__()
        self.close_calls = 0

    def close(self) -> None:
        """Record that someone closed the store."""
        self.close_calls += 1


def build_app(store: SessionStore | None = None):
    """An API with no environment reads except the store path, and a test model."""
    settings = ApiSettings(_env_file=None)  # pyright: ignore[reportCallIssue]
    return create_app(settings=settings, llm=FakeLLM(), store=store)


def test_the_suite_points_the_store_at_a_temporary_path(temporary_session_store_path: Path):
    """The autouse fixture makes the API's default store path a temporary one."""
    assert SessionStoreSettings().path == temporary_session_store_path
    assert temporary_session_store_path.is_absolute()


def test_an_injected_store_is_the_one_the_dependency_returns():
    """A store passed to create_app is the one routes receive through get_store."""
    store = InMemorySessionStore()
    app = build_app(store)

    @app.get("/same-store")
    def same_store(found: SessionStore = Depends(get_store)) -> dict[str, bool]:
        return {"same": found is store}

    with TestClient(app) as client:
        response = client.get("/same-store")

    assert response.json() == {"same": True}


def test_without_an_injected_store_the_api_opens_sqlite_and_creates_the_folder(
    temporary_session_store_path: Path,
):
    """With no store given, startup opens the SQLite file at SESSION_STORE_PATH."""
    assert not temporary_session_store_path.parent.exists()
    app = build_app()

    with TestClient(app):
        assert isinstance(app.state.store, SQLiteSessionStore)
        assert temporary_session_store_path.exists()


def test_the_api_closes_a_store_it_opened_itself():
    """A store the API built is closed at shutdown, so it refuses work afterwards."""
    app = build_app()

    with TestClient(app):
        store = app.state.store

    with pytest.raises(RuntimeError):
        asyncio.run(store.get_user_by_token_hash("any-hash"))


def test_the_api_does_not_close_a_store_it_was_given():
    """A caller that passes its own store stays responsible for closing it."""
    store = SpyStore()

    with TestClient(build_app(store)):
        pass

    assert store.close_calls == 0


def test_health_does_not_use_the_store():
    """GET /health works even when the store would refuse every call."""

    class BrokenStore(InMemorySessionStore):
        async def get_user_by_token_hash(self, token_hash: str):
            raise AssertionError("health must not touch the store")

    with TestClient(build_app(BrokenStore())) as client:
        response = client.get("/health")

    assert response.status_code == 200
