"""Anonymous identities and persistent preparation resources."""

import hashlib
import os
import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from contracts import Preparation, PreparationCreate
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/v1")


class IdentityResponse(BaseModel):
    user_id: str
    token: str
    created_at: datetime


class PreparationSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_title: str
    created_at: datetime
    session_count: int = 0
    last_session_at: datetime | None = None


def database_path() -> Path:
    """Use MOCKINA_DB_PATH when configured; otherwise keep data in the user's home."""
    configured = os.environ.get("MOCKINA_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "share" / "mockina" / "mockina.sqlite3"


def connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS identities (
                user_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS preparations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES identities(user_id)
                    ON DELETE CASCADE,
                job_title TEXT NOT NULL,
                job_description TEXT NOT NULL,
                resume TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS preparations_owner_created
                ON preparations(user_id, created_at DESC);
            """
        )


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def current_identity(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="A valid bearer token is required.")

    with connect(request.app.state.database_path) as db:
        row = db.execute(
            "SELECT user_id FROM identities WHERE token_hash = ?",
            (token_hash(token.strip()),),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=401, detail="The identity token is invalid.")
    return str(row["user_id"])


@router.post("/identity", response_model=IdentityResponse, status_code=201)
def create_identity(request: Request) -> IdentityResponse:
    user_id = str(uuid4())
    token = secrets.token_urlsafe(32)
    created_at = datetime.now(UTC)

    with connect(request.app.state.database_path) as db:
        db.execute(
            "INSERT INTO identities (user_id, token_hash, created_at) VALUES (?, ?, ?)",
            (user_id, token_hash(token), created_at.isoformat()),
        )

    return IdentityResponse(user_id=user_id, token=token, created_at=created_at)


@router.delete("/identity", status_code=204)
def delete_identity(
    request: Request,
    user_id: str = Depends(current_identity),
) -> None:
    with connect(request.app.state.database_path) as db:
        db.execute("DELETE FROM identities WHERE user_id = ?", (user_id,))


@router.post("/preparations", response_model=Preparation, status_code=201)
def create_preparation(
    body: PreparationCreate,
    request: Request,
    user_id: str = Depends(current_identity),
) -> Preparation:
    preparation = Preparation(**body.model_dump())

    with connect(request.app.state.database_path) as db:
        db.execute(
            """
            INSERT INTO preparations
                (id, user_id, job_title, job_description, resume, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(preparation.id),
                user_id,
                preparation.job_title,
                preparation.job_description,
                preparation.resume,
                preparation.created_at.isoformat(),
            ),
        )

    return preparation


@router.get("/preparations")
def list_preparations(
    request: Request,
    user_id: str = Depends(current_identity),
) -> dict[str, list[PreparationSummaryResponse]]:
    with connect(request.app.state.database_path) as db:
        rows = db.execute(
            """
            SELECT id, job_title, created_at
            FROM preparations
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()

    return {
        "items": [
            PreparationSummaryResponse(
                id=row["id"],
                job_title=row["job_title"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
    }


@router.get("/preparations/{preparation_id}", response_model=Preparation)
def get_preparation(
    preparation_id: UUID,
    request: Request,
    user_id: str = Depends(current_identity),
) -> Preparation:
    with connect(request.app.state.database_path) as db:
        row = db.execute(
            """
            SELECT id, job_title, job_description, resume, created_at
            FROM preparations
            WHERE id = ? AND user_id = ?
            """,
            (str(preparation_id), user_id),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Preparation not found.")

    return Preparation(
        id=row["id"],
        job_title=row["job_title"],
        job_description=row["job_description"],
        resume=row["resume"],
        created_at=row["created_at"],
    )
