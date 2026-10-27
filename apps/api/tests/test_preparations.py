"""Tests for the preparation routes: create, list, read, edit and delete."""

from typing import TYPE_CHECKING

import pytest
from contracts.preparation import (
    MAX_JOB_DESCRIPTION_LENGTH,
    MAX_JOB_TITLE_LENGTH,
    MAX_RESUME_LENGTH,
)
from fastapi.testclient import TestClient
from llm_gateway.testing import FakeLLM

if TYPE_CHECKING:
    from conftest import Credentials

BODY = {
    "job_title": "Junior React Developer",
    "job_description": "Build interfaces with React and TypeScript.",
    "resume": "Built a task tracker with React.",
}
MISSING_ID = "00000000-0000-4000-8000-000000000000"


def create(client: TestClient, user: "Credentials", body: dict | None = None) -> dict:
    """Create a preparation as the user and return the response body."""
    response = client.post("/v1/preparations", json=body or BODY, headers=user.headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_creating_a_preparation_returns_201_with_the_server_owned_fields(
    client: TestClient, user: "Credentials"
):
    """POST returns the stored Preparation: the sent fields plus an id and a creation time."""
    response = client.post("/v1/preparations", json=BODY, headers=user.headers)

    assert response.status_code == 201
    body = response.json()
    assert {k: body[k] for k in BODY} == BODY
    assert set(body) == {*BODY, "id", "created_at"}


def test_creating_a_preparation_does_not_call_the_model(
    client: TestClient, user: "Credentials", llm: FakeLLM
):
    """Skills are extracted lazily on the first question, so creating costs no model call."""
    create(client, user)

    assert llm.calls == []


def test_a_resume_is_optional(client: TestClient, user: "Credentials"):
    """A preparation without a resume is stored with resume null."""
    body = create(client, user, {"job_title": "Analyst", "job_description": "Write SQL."})

    assert body["resume"] is None


def test_text_fields_are_trimmed(client: TestClient, user: "Credentials"):
    """Leading and trailing whitespace is removed before the preparation is stored."""
    body = create(client, user, {"job_title": "  Analyst  ", "job_description": "\nWrite SQL.\n"})

    assert body["job_title"] == "Analyst"
    assert body["job_description"] == "Write SQL."


def test_the_longest_allowed_texts_are_accepted(client: TestClient, user: "Credentials"):
    """Texts exactly at the contract limits are valid."""
    create(
        client,
        user,
        {
            "job_title": "t" * MAX_JOB_TITLE_LENGTH,
            "job_description": "d" * MAX_JOB_DESCRIPTION_LENGTH,
            "resume": "r" * MAX_RESUME_LENGTH,
        },
    )


INVALID_BODIES = [
    pytest.param({"job_description": "Write SQL."}, id="missing-title"),
    pytest.param({"job_title": "Analyst"}, id="missing-description"),
    pytest.param({"job_title": "   ", "job_description": "Write SQL."}, id="blank-title"),
    pytest.param({"job_title": "Analyst", "job_description": ""}, id="empty-description"),
    pytest.param(
        {"job_title": "t" * (MAX_JOB_TITLE_LENGTH + 1), "job_description": "Write SQL."},
        id="title-too-long",
    ),
    pytest.param(
        {"job_title": "Analyst", "job_description": "d" * (MAX_JOB_DESCRIPTION_LENGTH + 1)},
        id="description-too-long",
    ),
    pytest.param(
        {"job_title": "Analyst", "job_description": "Write SQL.", "resume": ""},
        id="empty-resume",
    ),
    pytest.param(
        {"job_title": "Analyst", "job_description": "Write SQL.", "surprise": 1},
        id="unknown-field",
    ),
]


@pytest.mark.parametrize("body", INVALID_BODIES)
def test_an_invalid_preparation_is_rejected_without_echoing_it(
    client: TestClient, user: "Credentials", body: dict
):
    """Bad input gets the shared 422 error, and the text the user sent is not repeated."""
    response = client.post("/v1/preparations", json=body, headers=user.headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    for value in body.values():
        if isinstance(value, str) and len(value) > 12:
            assert value not in response.text


def test_the_list_is_empty_for_a_new_user(client: TestClient, user: "Credentials"):
    """A user with no preparations gets an empty items list."""
    response = client.get("/v1/preparations", headers=user.headers)

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_the_list_is_newest_first_with_session_counts(
    client: TestClient, user: "Credentials", clock
):
    """Summaries are ordered newest first and carry the counts the home page shows."""
    first = create(client, user, {**BODY, "job_title": "First"})
    clock.advance(minutes=5)
    second = create(client, user, {**BODY, "job_title": "Second"})
    client.post(f"/v1/preparations/{first['id']}/sessions", headers=user.headers)

    items = client.get("/v1/preparations", headers=user.headers).json()["items"]

    assert [item["id"] for item in items] == [second["id"], first["id"]]
    assert set(items[0]) == {"id", "job_title", "created_at", "session_count", "last_session_at"}
    assert items[0]["session_count"] == 0
    assert items[0]["last_session_at"] is None
    assert items[1]["session_count"] == 1
    assert items[1]["last_session_at"] is not None


def test_the_list_shows_only_the_callers_preparations(
    client: TestClient, user: "Credentials", other_user: "Credentials"
):
    """Another user's preparations never appear in the list."""
    mine = create(client, user)
    create(client, other_user, {**BODY, "job_title": "Not mine"})

    items = client.get("/v1/preparations", headers=user.headers).json()["items"]

    assert [item["id"] for item in items] == [mine["id"]]


def test_reading_one_preparation(client: TestClient, user: "Credentials"):
    """GET returns the same Preparation that POST returned."""
    created = create(client, user)

    response = client.get(f"/v1/preparations/{created['id']}", headers=user.headers)

    assert response.status_code == 200
    assert response.json() == created


def test_another_users_preparation_looks_exactly_like_a_missing_one(
    client: TestClient, user: "Credentials", other_user: "Credentials"
):
    """The 404 for someone else's preparation equals the 404 for one that never existed."""
    theirs = create(client, other_user)

    foreign = client.get(f"/v1/preparations/{theirs['id']}", headers=user.headers)
    missing = client.get(f"/v1/preparations/{MISSING_ID}", headers=user.headers)

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert foreign.json()["error"]["code"] == "not_found"


def test_a_malformed_id_is_a_422(client: TestClient, user: "Credentials"):
    """An id that is not a UUID is rejected as invalid input."""
    response = client.get("/v1/preparations/not-a-uuid", headers=user.headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_patch_changes_only_the_sent_fields(client: TestClient, user: "Credentials"):
    """A partial body leaves every field it does not mention as it was."""
    created = create(client, user)

    response = client.patch(
        f"/v1/preparations/{created['id']}", json={"job_title": "Senior Dev"}, headers=user.headers
    )

    assert response.status_code == 200
    assert response.json() == {**created, "job_title": "Senior Dev"}
    stored = client.get(f"/v1/preparations/{created['id']}", headers=user.headers).json()
    assert stored == response.json()


def test_patch_can_clear_the_resume_with_null(client: TestClient, user: "Credentials"):
    """Sending resume null removes it; leaving it out keeps it."""
    created = create(client, user)

    kept = client.patch(
        f"/v1/preparations/{created['id']}", json={"job_title": "Dev"}, headers=user.headers
    )
    cleared = client.patch(
        f"/v1/preparations/{created['id']}", json={"resume": None}, headers=user.headers
    )

    assert kept.json()["resume"] == BODY["resume"]
    assert cleared.json()["resume"] is None


PATCH_REJECTED = [
    pytest.param({}, id="empty-body"),
    pytest.param({"job_title": None}, id="null-title"),
    pytest.param({"job_description": None}, id="null-description"),
    pytest.param({"job_title": "  "}, id="blank-title"),
    pytest.param({"job_title": "t" * (MAX_JOB_TITLE_LENGTH + 1)}, id="title-too-long"),
    pytest.param({"resume": ""}, id="empty-resume"),
    pytest.param({"surprise": 1}, id="unknown-field"),
]


@pytest.mark.parametrize("body", PATCH_REJECTED)
def test_patch_rejects_bodies_that_change_nothing_or_break_a_rule(
    client: TestClient, user: "Credentials", body: dict
):
    """An empty body, a null title or description, and out-of-range text are all 422."""
    created = create(client, user)

    response = client.patch(f"/v1/preparations/{created['id']}", json=body, headers=user.headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    unchanged = client.get(f"/v1/preparations/{created['id']}", headers=user.headers).json()
    assert unchanged == created


def test_patch_is_refused_once_a_session_exists(client: TestClient, user: "Credentials"):
    """After the first session the preparation is locked: 409 preparation_locked."""
    created = create(client, user)
    client.post(f"/v1/preparations/{created['id']}/sessions", headers=user.headers)

    response = client.patch(
        f"/v1/preparations/{created['id']}", json={"job_title": "Dev"}, headers=user.headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "preparation_locked"


def test_patching_another_users_preparation_is_a_404(
    client: TestClient, user: "Credentials", other_user: "Credentials"
):
    """Editing somebody else's preparation behaves like editing a missing one."""
    theirs = create(client, other_user)

    response = client.patch(
        f"/v1/preparations/{theirs['id']}", json={"job_title": "Mine now"}, headers=user.headers
    )

    assert response.status_code == 404
    unchanged = client.get(f"/v1/preparations/{theirs['id']}", headers=other_user.headers).json()
    assert unchanged == theirs


def test_deleting_a_preparation_returns_204_and_removes_its_sessions(
    client: TestClient, user: "Credentials"
):
    """DELETE answers 204 and the preparation and its sessions are gone."""
    created = create(client, user)
    session = client.post(f"/v1/preparations/{created['id']}/sessions", headers=user.headers).json()

    response = client.delete(f"/v1/preparations/{created['id']}", headers=user.headers)

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/v1/preparations/{created['id']}", headers=user.headers).status_code == 404
    assert client.get(f"/v1/sessions/{session['id']}", headers=user.headers).status_code == 404
    assert (
        client.delete(f"/v1/preparations/{created['id']}", headers=user.headers).status_code == 404
    )


def test_deleting_another_users_preparation_is_a_404_and_changes_nothing(
    client: TestClient, user: "Credentials", other_user: "Credentials"
):
    """One user cannot delete another's preparation."""
    theirs = create(client, other_user)

    response = client.delete(f"/v1/preparations/{theirs['id']}", headers=user.headers)

    assert response.status_code == 404
    assert (
        client.get(f"/v1/preparations/{theirs['id']}", headers=other_user.headers).status_code
        == 200
    )
