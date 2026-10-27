"""Tests for browser access rules: which origins, methods and headers the API accepts."""

import pytest
from fastapi.testclient import TestClient

ORIGIN = "http://localhost:5173"


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_preflight_allows_every_method_the_product_api_uses(client: TestClient, method: str):
    """The browser may send GET, POST, PUT, PATCH and DELETE from the configured origin."""
    response = client.options(
        "/v1/preparations",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert method in response.headers["access-control-allow-methods"]


def test_preflight_allows_the_authorization_header(client: TestClient):
    """The bearer token travels in Authorization, so preflight must accept that header."""
    response = client.options(
        "/v1/identity",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_preflight_rejects_a_header_the_api_does_not_use(client: TestClient):
    """A request header outside the allowed list is refused at preflight."""
    response = client.options(
        "/v1/preparations",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-surprise",
        },
    )

    assert response.status_code == 400


def test_preflight_answers_are_cached_by_the_browser(client: TestClient):
    """Preflight replies carry a max age, so the browser does not repeat them on every call."""
    response = client.options(
        "/v1/preparations",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert int(response.headers["access-control-max-age"]) >= 600


def test_retry_after_can_be_read_by_browser_code(client: TestClient):
    """The browser client reads Retry-After, so cross-origin responses must expose it."""
    response = client.get("/health", headers={"Origin": ORIGIN})

    exposed = response.headers["access-control-expose-headers"].lower()
    assert "retry-after" in exposed
