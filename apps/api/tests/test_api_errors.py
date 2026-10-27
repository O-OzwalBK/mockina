"""Tests for the product error type and the mapping of store errors to HTTP answers."""

import logging

import pytest
from api.errors import STORE_ERROR_MAP, ApiError
from api.main import create_app
from api.settings import ApiSettings
from contracts import Question, Turn
from fastapi.testclient import TestClient
from llm_gateway.testing import FakeLLM
from session_store import (
    InMemorySessionStore,
    InvalidStateError,
    NotFoundError,
    OpenQuestionError,
    PreparationLockedError,
    SessionFullError,
    SessionStoreError,
)

PRIVATE_TEXT = "private-job-description-marker"


def open_turn() -> Turn:
    """A real unanswered turn, which is what OpenQuestionError carries."""
    question = Question(text="What is a closure?", skill_id="javascript", difficulty=2)
    return Turn(question=question)


def app_that_raises(error: Exception):
    """An API with one extra route, `/boom`, that raises the given error when called."""
    settings = ApiSettings(_env_file=None)  # pyright: ignore[reportCallIssue]
    app = create_app(settings=settings, llm=FakeLLM(), store=InMemorySessionStore())

    @app.get("/boom")
    def boom() -> None:
        raise error

    return app


def test_api_error_uses_the_shared_error_envelope():
    """An ApiError becomes its status, the shared JSON envelope and any extra headers."""
    error = ApiError(
        409,
        "custom_conflict",
        "A safe message.",
        retryable=True,
        details={"field": "title"},
        headers={"Retry-After": "3"},
    )

    with TestClient(app_that_raises(error)) as client:
        response = client.get("/boom")

    assert response.status_code == 409
    assert response.headers["retry-after"] == "3"
    assert response.json() == {
        "error": {
            "code": "custom_conflict",
            "message": "A safe message.",
            "retryable": True,
            "details": {"field": "title"},
        }
    }


def test_api_error_defaults_to_not_retryable_with_no_details():
    """Unless a caller says otherwise, an ApiError is not retryable and has empty details."""
    with TestClient(app_that_raises(ApiError(401, "unauthorized", "Sign in first."))) as client:
        response = client.get("/boom")

    assert response.json()["error"]["retryable"] is False
    assert response.json()["error"]["details"] == {}


STORE_CASES = [
    (NotFoundError(PRIVATE_TEXT), 404, "not_found"),
    (PreparationLockedError(PRIVATE_TEXT), 409, "preparation_locked"),
    (InvalidStateError(PRIVATE_TEXT), 409, "invalid_state"),
    (SessionFullError(PRIVATE_TEXT), 409, "session_finished"),
    (OpenQuestionError(open_turn()), 409, "invalid_state"),
]


def test_store_case_list_is_not_empty():
    """Guard: the parametrized store-error checks must always have cases."""
    assert STORE_CASES


@pytest.mark.parametrize(("error", "status", "code"), STORE_CASES)
def test_store_errors_map_to_their_status_and_code(error, status, code):
    """Each store error becomes its documented status and stable code, and is not retryable."""
    with TestClient(app_that_raises(error)) as client:
        response = client.get("/boom")

    payload = response.json()["error"]
    assert response.status_code == status
    assert payload["code"] == code
    assert payload["retryable"] is False
    assert payload["details"] == {}


@pytest.mark.parametrize(("error", "status", "code"), STORE_CASES)
def test_store_error_text_never_reaches_the_response_or_the_log(
    error, status, code, caplog: pytest.LogCaptureFixture
):
    """The answer carries a fixed message, so text inside a store error cannot leak."""
    caplog.set_level(logging.DEBUG)
    with TestClient(app_that_raises(error)) as client:
        response = client.get("/boom")

    assert PRIVATE_TEXT not in response.text
    assert PRIVATE_TEXT not in caplog.text


def test_every_store_error_has_a_mapping():
    """Every concrete error exported by session_store has an HTTP mapping."""
    exported_errors = {
        error
        for error in SessionStoreError.__subclasses__()
        if error.__module__.startswith("session_store")
    }
    assert exported_errors
    assert exported_errors == set(STORE_ERROR_MAP)


def test_an_unmapped_store_error_is_a_generic_500():
    """A store error nobody mapped gives the generic internal error, never its own text."""

    class Surprise(SessionStoreError):
        """A store failure the API has no mapping for."""

    with TestClient(
        app_that_raises(Surprise(PRIVATE_TEXT)), raise_server_exceptions=False
    ) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert PRIVATE_TEXT not in response.text
