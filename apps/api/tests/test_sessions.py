"""Tests for the session routes: start, list, read, complete and abandon."""

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

from contracts import Answer, Question
from fastapi.testclient import TestClient
from session_store import InMemorySessionStore

if TYPE_CHECKING:
    from conftest import Credentials

BODY = {
    "job_title": "Junior React Developer",
    "job_description": "Build interfaces with React and TypeScript.",
}
MISSING_ID = "00000000-0000-4000-8000-000000000000"


def make_preparation(client: TestClient, user: "Credentials") -> str:
    """Create a preparation as the user and return its id."""
    return client.post("/v1/preparations", json=BODY, headers=user.headers).json()["id"]


def make_session(client: TestClient, user: "Credentials") -> str:
    """Create a preparation and an empty session for the user, and return the session id."""
    preparation_id = make_preparation(client, user)
    response = client.post(f"/v1/preparations/{preparation_id}/sessions", headers=user.headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def ask_and_answer(
    store: InMemorySessionStore, user: "Credentials", session_id: str, *, answer: bool = True
) -> Question:
    """Put one question in the session through the store, and answer it unless told not to."""
    question = Question(text="What is a closure?", skill_id="javascript", difficulty=2)
    owner, session = user.user_id, UUID(session_id)
    asyncio.run(store.add_question(owner, session, question))
    if answer:
        asyncio.run(
            store.record_answer(
                owner,
                session,
                question.id,
                Answer(transcript="A function and its scope.", duration=9),
            )
        )
    return question


def test_starting_a_session_returns_201_and_an_empty_in_progress_session(
    client: TestClient, user: "Credentials"
):
    """POST creates a session with no turns, in progress and with no end time."""
    preparation_id = make_preparation(client, user)

    response = client.post(f"/v1/preparations/{preparation_id}/sessions", headers=user.headers)

    assert response.status_code == 201
    body = response.json()
    assert body["preparation_id"] == preparation_id
    assert body["status"] == "in_progress"
    assert body["turns"] == []
    assert body["ended_at"] is None


def test_starting_a_session_does_not_call_the_model(client: TestClient, user: "Credentials", llm):
    """The first question is asked by its own route, so starting a session costs no model call."""
    make_session(client, user)

    assert llm.calls == []


def test_starting_a_session_on_a_missing_or_foreign_preparation_is_a_404(
    client: TestClient, user: "Credentials", other_user: "Credentials"
):
    """Another user's preparation behaves like a missing one."""
    theirs = make_preparation(client, other_user)

    foreign = client.post(f"/v1/preparations/{theirs}/sessions", headers=user.headers)
    missing = client.post(f"/v1/preparations/{MISSING_ID}/sessions", headers=user.headers)

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_listing_sessions_newest_first_with_progress_counts(
    client: TestClient, user: "Credentials", clock
):
    """Summaries are newest first and carry turns_total and turns_graded."""
    preparation_id = make_preparation(client, user)
    first = client.post(f"/v1/preparations/{preparation_id}/sessions", headers=user.headers).json()
    clock.advance(minutes=10)
    second = client.post(f"/v1/preparations/{preparation_id}/sessions", headers=user.headers).json()

    response = client.get(f"/v1/preparations/{preparation_id}/sessions", headers=user.headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [second["id"], first["id"]]
    assert set(items[0]) == {
        "id",
        "preparation_id",
        "status",
        "started_at",
        "ended_at",
        "turns_total",
        "turns_graded",
    }
    assert items[0]["turns_total"] == 0
    assert items[0]["turns_graded"] == 0


def test_listing_sessions_of_a_missing_or_foreign_preparation_is_a_404(
    client: TestClient, user: "Credentials", other_user: "Credentials"
):
    """There is no list to show for a preparation the caller does not own, though the route exists."""
    mine = make_preparation(client, user)
    theirs = make_preparation(client, other_user)

    own = client.get(f"/v1/preparations/{mine}/sessions", headers=user.headers)
    foreign = client.get(f"/v1/preparations/{theirs}/sessions", headers=user.headers)
    missing = client.get(f"/v1/preparations/{MISSING_ID}/sessions", headers=user.headers)

    assert own.status_code == 200
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_reading_a_session_returns_its_turns_with_answers(
    client: TestClient, user: "Credentials", store: InMemorySessionStore
):
    """GET /v1/sessions/{id} returns the full session, including each turn's answer."""
    session_id = make_session(client, user)
    question = ask_and_answer(store, user, session_id)

    response = client.get(f"/v1/sessions/{session_id}", headers=user.headers)

    assert response.status_code == 200
    turn = response.json()["turns"][0]
    assert turn["question"]["id"] == str(question.id)
    assert turn["status"] == "awaiting_grade"
    assert turn["answer"]["transcript"] == "A function and its scope."


def test_another_users_session_looks_exactly_like_a_missing_one(
    client: TestClient, user: "Credentials", other_user: "Credentials"
):
    """The 404 for someone else's session equals the 404 for one that never existed."""
    theirs = make_session(client, other_user)

    foreign = client.get(f"/v1/sessions/{theirs}", headers=user.headers)
    missing = client.get(f"/v1/sessions/{MISSING_ID}", headers=user.headers)

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_completing_a_session_with_no_answered_turn_is_a_409(
    client: TestClient, user: "Credentials"
):
    """A session needs at least one answered question before it can be completed."""
    session_id = make_session(client, user)

    response = client.post(f"/v1/sessions/{session_id}/complete", headers=user.headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_completing_a_session_returns_a_summary_and_sets_the_end_time(
    client: TestClient, user: "Credentials", store: InMemorySessionStore
):
    """Completion returns the SessionSummary with status completed and an end time."""
    session_id = make_session(client, user)
    ask_and_answer(store, user, session_id)

    response = client.post(f"/v1/sessions/{session_id}/complete", headers=user.headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == session_id
    assert body["status"] == "completed"
    assert body["ended_at"] is not None
    assert body["turns_total"] == 1


def test_completing_drops_an_unanswered_last_question(
    client: TestClient, user: "Credentials", store: InMemorySessionStore
):
    """A question still waiting for its answer is removed when the session completes."""
    session_id = make_session(client, user)
    ask_and_answer(store, user, session_id)
    ask_and_answer(store, user, session_id, answer=False)

    body = client.post(f"/v1/sessions/{session_id}/complete", headers=user.headers).json()

    assert body["turns_total"] == 1


def test_completing_twice_gives_the_same_answer(
    client: TestClient, user: "Credentials", store: InMemorySessionStore
):
    """Completing an already completed session is harmless: the same summary comes back."""
    session_id = make_session(client, user)
    ask_and_answer(store, user, session_id)

    first = client.post(f"/v1/sessions/{session_id}/complete", headers=user.headers)
    second = client.post(f"/v1/sessions/{session_id}/complete", headers=user.headers)

    assert second.status_code == 200
    assert second.json() == first.json()


def test_abandoning_a_session_needs_no_answer(client: TestClient, user: "Credentials"):
    """A session with no turns can still be abandoned, and the summary says so."""
    session_id = make_session(client, user)

    response = client.post(f"/v1/sessions/{session_id}/abandon", headers=user.headers)

    assert response.status_code == 200
    assert response.json()["status"] == "abandoned"
    assert response.json()["ended_at"] is not None


def test_abandoning_twice_is_harmless(client: TestClient, user: "Credentials"):
    """Abandoning an abandoned session returns the same summary."""
    session_id = make_session(client, user)

    first = client.post(f"/v1/sessions/{session_id}/abandon", headers=user.headers)
    second = client.post(f"/v1/sessions/{session_id}/abandon", headers=user.headers)

    assert second.status_code == 200
    assert second.json() == first.json()


def test_a_finished_session_cannot_switch_to_the_other_ending(
    client: TestClient, user: "Credentials", store: InMemorySessionStore
):
    """Completed stays completed and abandoned stays abandoned: the other call is a 409."""
    completed = make_session(client, user)
    ask_and_answer(store, user, completed)
    client.post(f"/v1/sessions/{completed}/complete", headers=user.headers)
    abandoned = make_session(client, user)
    client.post(f"/v1/sessions/{abandoned}/abandon", headers=user.headers)

    abandon_completed = client.post(f"/v1/sessions/{completed}/abandon", headers=user.headers)
    complete_abandoned = client.post(f"/v1/sessions/{abandoned}/complete", headers=user.headers)

    assert abandon_completed.status_code == complete_abandoned.status_code == 409
    assert abandon_completed.json()["error"]["code"] == "invalid_state"


def test_another_user_cannot_complete_or_abandon_a_session(
    client: TestClient, user: "Credentials", other_user: "Credentials"
):
    """Ending somebody else's session behaves like ending a missing one, and changes nothing."""
    theirs = make_session(client, other_user)

    complete = client.post(f"/v1/sessions/{theirs}/complete", headers=user.headers)
    abandon = client.post(f"/v1/sessions/{theirs}/abandon", headers=user.headers)

    assert complete.status_code == abandon.status_code == 404
    still = client.get(f"/v1/sessions/{theirs}", headers=other_user.headers).json()
    assert still["status"] == "in_progress"
