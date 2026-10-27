"""Tests for bearer authentication and the rule that every product route is protected."""

import asyncio
import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from api.auth import CurrentUser, hash_token
from fastapi import FastAPI
from fastapi.testclient import TestClient
from session_store import InMemorySessionStore

if TYPE_CHECKING:
    from conftest import Credentials, MutableClock


UNAUTHORIZED_BODY = {
    "error": {
        "code": "unauthorized",
        "message": "A valid bearer token is required.",
        "retryable": False,
        "details": {},
    }
}


@pytest.fixture
def probe_client(app: FastAPI, client: TestClient) -> TestClient:
    """The client, plus a `/probe` route that only reports who is calling."""

    @app.get("/probe")
    def probe(user: CurrentUser) -> dict[str, str]:
        return {"user_id": str(user.id)}

    return client


def test_a_valid_token_reaches_the_route_as_its_user(
    probe_client: TestClient, mint_identity: Callable[[], "Credentials"]
):
    """A good bearer token resolves to its user."""
    credentials = mint_identity()

    response = probe_client.get("/probe", headers=credentials.headers)

    assert response.status_code == 200
    assert response.json() == {"user_id": str(credentials.user_id)}


def test_the_bearer_scheme_name_is_case_insensitive(
    probe_client: TestClient, mint_identity: Callable[[], "Credentials"]
):
    """`bearer <token>` works as well as `Bearer <token>`, as HTTP allows."""
    credentials = mint_identity()

    response = probe_client.get("/probe", headers={"Authorization": f"bearer {credentials.token}"})

    assert response.status_code == 200


BAD_AUTHORIZATION_HEADERS = [
    pytest.param(None, id="no-header"),
    pytest.param("Bearer ", id="empty-token"),
    pytest.param("Bearer not-a-real-token", id="unknown-token"),
    pytest.param("Basic dXNlcjpwYXNz", id="wrong-scheme"),
    pytest.param("Token abc", id="invented-scheme"),
]


@pytest.mark.parametrize("authorization", BAD_AUTHORIZATION_HEADERS)
def test_missing_or_unknown_credentials_all_give_the_same_401(
    probe_client: TestClient, authorization: str | None
):
    """Absent, malformed and unknown tokens are indistinguishable to the caller."""
    headers = {} if authorization is None else {"Authorization": authorization}

    response = probe_client.get("/probe", headers=headers)

    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED_BODY
    assert response.headers["www-authenticate"] == "Bearer"


def test_a_deleted_users_token_is_unknown(
    probe_client: TestClient,
    store: InMemorySessionStore,
    mint_identity: Callable[[], "Credentials"],
):
    """Once the user is gone, the token gives the same 401 as any unknown token."""
    credentials = mint_identity()
    asyncio.run(store.delete_user(credentials.user_id))

    response = probe_client.get("/probe", headers=credentials.headers)

    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED_BODY


def test_using_a_token_refreshes_last_seen_at_most_once_a_day(
    probe_client: TestClient,
    store: InMemorySessionStore,
    clock: "MutableClock",
    mint_identity: Callable[[], "Credentials"],
):
    """Authenticating touches the user, and the store keeps that to one write per UTC day."""
    credentials = mint_identity()
    token_hash = hash_token(credentials.token)
    created = clock.current

    clock.advance(days=2)
    probe_client.get("/probe", headers=credentials.headers)
    touched = asyncio.run(store.get_user_by_token_hash(token_hash))
    assert touched is not None
    assert touched.last_seen_at == clock.current != created

    first_touch = clock.current
    clock.advance(hours=1)
    probe_client.get("/probe", headers=credentials.headers)
    again = asyncio.run(store.get_user_by_token_hash(token_hash))
    assert again is not None
    assert again.last_seen_at == first_touch


def test_a_rejected_token_never_appears_in_the_response_or_the_log(
    probe_client: TestClient, caplog: pytest.LogCaptureFixture
):
    """Neither a bad token nor its hash is echoed back or written to the log."""
    marker = "secret-token-marker-0123456789"
    caplog.set_level(logging.DEBUG)

    response = probe_client.get("/probe", headers={"Authorization": f"Bearer {marker}"})

    assert marker not in response.text
    assert marker not in caplog.text
    assert hash_token(marker) not in caplog.text


def test_the_bearer_scheme_is_documented_in_openapi(client: TestClient):
    """OpenAPI declares bearer auth, and the identity deletion route says it needs it."""
    schema = client.get("/openapi.json").json()

    schemes = schema["components"]["securitySchemes"]
    assert any(item["type"] == "http" and item["scheme"] == "bearer" for item in schemes.values())
    assert schema["paths"]["/v1/identity"]["delete"]["security"]
    assert "security" not in schema["paths"]["/v1/identity"]["post"]


def test_the_route_matrix_sees_the_public_and_protected_routes(product_operations, public_routes):
    """Guard: the matrix below must find routes, or it would pass while checking nothing."""
    found = {(method, path) for method, path, _ in product_operations}
    assert public_routes <= found
    assert ("DELETE", "/v1/identity") in found


def test_every_product_route_except_the_public_ones_requires_a_token(
    product_operations, public_routes, client: TestClient
):
    """Calling any other /v1 route with no token gives the 401 error, whatever its method."""
    protected = [
        (method, path)
        for method, path, _ in product_operations
        if (method, path) not in public_routes
    ]
    assert protected

    for method, path in protected:
        concrete = re.sub(r"\{[^}]+\}", "00000000-0000-4000-8000-000000000000", path)
        response = client.request(method, concrete)
        assert response.status_code == 401, f"{method} {path} answered {response.status_code}"
        assert response.json() == UNAUTHORIZED_BODY, f"{method} {path}"


def test_the_public_routes_need_no_token(client: TestClient):
    """Capabilities and identity creation work without credentials."""
    assert client.get("/v1/capabilities").status_code == 200
    assert client.post("/v1/identity").status_code == 201
