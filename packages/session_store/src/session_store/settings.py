"""Where the durable session database lives."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SessionStoreSettings(BaseSettings):
    """Settings for the SQLite session store, read from `SESSION_STORE_*`.

    The path is resolved relative to the process working directory unless an
    absolute path is supplied. The default folder is git-ignored.
    """

    model_config = SettingsConfigDict(
        env_prefix="SESSION_STORE_",
        env_file=("../../.env", ".env"),
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        str_strip_whitespace=True,
    )

    path: Path = Field(
        default=Path("data/session-store.sqlite3"),
        description="Path of the SQLite database file used for durable session storage.",
        examples=["data/session-store.sqlite3"],
    )
