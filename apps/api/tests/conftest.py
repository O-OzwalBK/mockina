"""Test setup shared by every API test file."""

from pathlib import Path

import pytest


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
