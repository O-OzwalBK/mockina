"""Tests for anonymous identities: token creation, hashing, and deleting all of a user's data."""

import asyncio
import hashlib
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from api.auth import generate_token, hash_token
from contracts import PreparationCreate, SkillGraph, skill_id
from fastapi.testclient import TestClient
from session_store import InMemorySessionStore
from skill_graph import InMemorySkillStore

if TYPE_CHECKING:
    from conftest import Credentials


SHA256_OF_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_hash_token_is_the_sha256_hex_digest():
    """A token is stored as its SHA-256 hex digest, never as the token itself."""
    assert hash_token("abc") == SHA256_OF_ABC
    assert hash_token("abc") == hashlib.sha256(b"abc").hexdigest()


def test_generated_tokens_are_long_unique_and_url_safe():
    """Tokens carry enough randomness to be unguessable and can travel in a header."""
    tokens = {generate_token() for _ in range(50)}
    assert len(tokens) == 50
    for token in tokens:
        assert len(token) >= 43  # 32 random bytes in URL-safe base64
        assert re.fullmatch(r"[A-Za-z0-9_-]+", token)


def test_creating_an_identity_returns_201_with_the_token(client: TestClient):
    """POST /v1/identity needs no token and returns the user id, a token and the creation time."""
    response = client.post("/v1/identity")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"user_id", "token", "created_at"}
    assert len(body["token"]) >= 43


def test_the_store_keeps_only_the_hash_of_the_token(
    client: TestClient, store: InMemorySessionStore
):
    """The raw token is shown once; the store can find the user only by its hash."""
    body = client.post("/v1/identity").json()

    by_hash = asyncio.run(store.get_user_by_token_hash(hash_token(body["token"])))
    by_raw_token = asyncio.run(store.get_user_by_token_hash(body["token"]))

    assert by_hash is not None
    assert str(by_hash.id) == body["user_id"]
    assert by_hash.token_hash == hash_token(body["token"])
    assert by_hash.token_hash != body["token"]
    assert by_raw_token is None


def test_every_identity_gets_its_own_token(client: TestClient):
    """Two calls mint two different users with two different tokens."""
    first = client.post("/v1/identity").json()
    second = client.post("/v1/identity").json()

    assert first["user_id"] != second["user_id"]
    assert first["token"] != second["token"]


def test_deleting_an_identity_returns_204_and_the_token_stops_working(
    client: TestClient, mint_identity: Callable[[], "Credentials"]
):
    """DELETE /v1/identity answers 204 with no body, and the same token is then rejected."""
    credentials = mint_identity()

    deleted = client.delete("/v1/identity", headers=credentials.headers)
    again = client.delete("/v1/identity", headers=credentials.headers)

    assert deleted.status_code == 204
    assert deleted.content == b""
    assert again.status_code == 401


def test_deleting_an_identity_deletes_its_preparations(
    client: TestClient,
    store: InMemorySessionStore,
    mint_identity: Callable[[], "Credentials"],
):
    """Everything the user owned in the store disappears with the identity."""
    credentials = mint_identity()
    preparation = asyncio.run(
        store.create_preparation(
            credentials.user_id,
            PreparationCreate(
                job_title="Junior React Developer",
                job_description="Build interfaces with React and TypeScript.",
            ),
        )
    )

    client.delete("/v1/identity", headers=credentials.headers)

    assert asyncio.run(store.get_preparation(credentials.user_id, preparation.id)) is None


def test_deleting_an_identity_does_not_touch_another_user(
    client: TestClient,
    store: InMemorySessionStore,
    mint_identity: Callable[[], "Credentials"],
):
    """Only the caller's data is deleted; another user keeps theirs and their token."""
    leaving = mint_identity()
    staying = mint_identity()
    kept = asyncio.run(
        store.create_preparation(
            staying.user_id,
            PreparationCreate(job_title="Data Analyst", job_description="Write SQL reports."),
        )
    )

    client.delete("/v1/identity", headers=leaving.headers)

    assert asyncio.run(store.get_preparation(staying.user_id, kept.id)) is not None
    assert client.delete("/v1/identity", headers=staying.headers).status_code == 204


def graph_with_leaf(label: str) -> SkillGraph:
    """A small valid skill graph: one root and three leaves, one of them named by the caller."""
    root = skill_id("React", "React")
    leaves = [label, "Effect hooks", "Built-in hooks"]
    return SkillGraph.model_validate(
        {
            "nodes": [
                {"id": root, "label": "React", "parent_id": None},
                *[
                    {
                        "id": skill_id("React", leaf),
                        "label": leaf,
                        "parent_id": root,
                        "importance": 3,
                        "difficulty": 2,
                    }
                    for leaf in leaves
                ],
            ]
        }
    )


def test_deleting_an_identity_forgets_the_skill_labels_learned_from_its_job_text(
    client: TestClient,
    skill_store: InMemorySkillStore,
    mint_identity: Callable[[], "Credentials"],
):
    """Skill labels extracted from a user's job description are deleted with the user."""
    credentials = mint_identity()
    owner = str(credentials.user_id)
    asyncio.run(skill_store.catalog.record(graph_with_leaf("Suspense boundaries"), owner))
    before = {e.node_label for e in asyncio.run(skill_store.catalog.all_entries(owner))}
    assert "Suspense boundaries" in before

    client.delete("/v1/identity", headers=credentials.headers)

    after = {e.node_label for e in asyncio.run(skill_store.catalog.all_entries(owner))}
    assert "Suspense boundaries" not in after
