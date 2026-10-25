from pathlib import Path

import pytest
from pydantic import ValidationError
from session_store.settings import SessionStoreSettings


def load() -> SessionStoreSettings:
    """Read settings from the environment only, ignoring any .env file."""
    return SessionStoreSettings(_env_file=None)  # pyright: ignore[reportCallIssue]


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    """Run every test with no SESSION_STORE_ variables set."""
    monkeypatch.delenv("SESSION_STORE_PATH", raising=False)


def test_the_default_path_is_in_the_git_ignored_data_folder():
    """A fresh install writes its database under data/ without configuration."""
    assert load().path == Path("data/session-store.sqlite3")


def test_the_path_can_be_overridden_from_the_environment(monkeypatch, tmp_path):
    """SESSION_STORE_PATH replaces the default path."""
    target = tmp_path / "sessions.db"
    monkeypatch.setenv("SESSION_STORE_PATH", str(target))
    assert load().path == target


def test_settings_are_frozen():
    """Settings cannot be changed after loading."""
    settings = load()
    with pytest.raises(ValidationError):
        settings.path = Path("other.db")


def test_other_prefixes_are_ignored(monkeypatch):
    """A variable without the SESSION_STORE_ prefix does not affect the path."""
    monkeypatch.setenv("PATH", "not-the-store-path")
    assert load().path == Path("data/session-store.sqlite3")
