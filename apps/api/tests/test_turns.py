"""Tests for POST /v1/sessions/{id}/turns, using a scripted question source instead of a model."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from contracts import Answer, Question
from contracts.session import MAX_TURNS_PER_SESSION
from engine import FinishedReason, InterviewFinished
from fastapi.testclient import TestClient
from llm_gateway import LLMTimeoutError
from session_store import InMemorySessionStore

if TYPE_CHECKING:
    from conftest import Credentials, FakeInterviewer

JOB = {
    "job_title": "Junior React Developer",
    "job_description": "Build User interfaces with React and TypeScript.",
}


def question(text: str = "How do React hooks work?", skill_id: str = "react-hooks") -> Question:
    """A valid question, with a fresh id each time."""
    return Question(text=text, skill_id=skill_id, difficulty=2)


def start_session(client: TestClient, credentials: Credentials, preparation_id: str | None = None):
    """Create a preparation (unless one is given) and a session on it; return both ids."""
    if preparation_id is None:
        created = client.post("/v1/preparations", json=JOB, headers=credentials.headers)
        preparation_id = created.json()["id"]

    session = client.post(
        f"/v1/preparations/{preparation_id}/sessions", headers=credentials.headers
    )

    return preparation_id, session.json()["id"]


def ask(client: TestClient, credentials: "Credentials", session_id: str):
    """Call the route under test."""
    return client.post(f"/v1/sessions/{session_id}/turns", headers=credentials.headers)


def answer(
    store: InMemorySessionStore, credentials: "Credentials", session_id: str, question_id: str
) -> None:
    """Answer a question directly in the store, as the answer route will later do."""
    asyncio.run(
        store.record_answer(
            credentials.user_id,
            UUID(session_id),
            UUID(question_id),
            Answer(transcript="An answer.", duration=5.0),
        )
    )


def test_the_first_request_asks_a_new_question_and_stores_it(
    client: TestClient, user: "Credentials", interviewer: "FakeInterviewer"
):
    """With no open question, the route asks for one and answers 201 with the new turn."""
    first = question("How do React hooks work?")
    interviewer.add(first)
    _, session_id = start_session(client, user)

    response = ask(client, user, session_id)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "awaiting_answer"
    assert body["answer"] is None
    assert body["question"]["id"] == str(first.id)
    assert body["question"]["text"] == "How do React hooks work?"
    stored = client.get(f"/v1/sessions/{session_id}", headers=user.headers).json()
    assert [turn["question"]["id"] for turn in stored["turns"]] == [str(first.id)]


def test_asking_again_returns_the_open_question_without_calling_the_model(
    client: TestClient, user: "Credentials", interviewer: "FakeInterviewer"
):
    """A repeated request (for example a client retry) gets the same question, with 200."""
    interviewer.add(question())
    _, session_id = start_session(client, user)
    first = ask(client, user, session_id)

    again = ask(client, user, session_id)

    assert first.status_code == 201
    assert again.status_code == 200
    assert again.json() == first.json()
    assert len(interviewer.calls) == 1


def test_a_new_question_follows_once_the_open_one_is_answered(
    client: TestClient,
    user: "Credentials",
    store: InMemorySessionStore,
    interviewer: "FakeInterviewer",
):
    """After an answer, the route asks again, and the interviewer sees the turn so far."""
    interviewer.add(question("How do React hooks work?"), question("What is a closure?"))
    _, session_id = start_session(client, user)
    first = ask(client, user, session_id).json()
    answer(store, user, session_id, first["question"]["id"])

    second = ask(client, user, session_id)

    assert second.status_code == 201
    assert second.json()["question"]["text"] == "What is a closure?"
    assert [t.question.id for t in interviewer.calls[1].turns] == [UUID(first["question"]["id"])]


def test_the_interviewer_gets_the_questions_of_other_sessions_but_not_of_this_one(
    client: TestClient,
    user: "Credentials",
    store: InMemorySessionStore,
    interviewer: "FakeInterviewer",
):
    """Earlier questions come from the preparation's other sessions; this session's are turns."""
    in_a, in_b = question("How do hooks work?"), question("What is a closure?")
    interviewer.add(in_a, in_b, question("What is a promise?"))
    preparation_id, session_a = start_session(client, user)
    answer(store, user, session_a, ask(client, user, session_a).json()["question"]["id"])
    _, session_b = start_session(client, user, preparation_id)

    ask(client, user, session_b)
    answer(store, user, session_b, str(in_b.id))
    ask(client, user, session_b)

    first_in_b, second_in_b = interviewer.calls[1], interviewer.calls[2]
    assert [q.id for q in first_in_b.earlier_questions] == [in_a.id]
    assert first_in_b.turns == ()
    assert [q.id for q in second_in_b.earlier_questions] == [in_a.id]
    assert [t.question.id for t in second_in_b.turns] == [in_b.id]


def test_the_interviewer_is_told_who_is_asking_and_about_which_preparation(
    client: TestClient, user: "Credentials", interviewer: "FakeInterviewer"
):
    """The question source receives the signed-in user and the stored preparation."""
    interviewer.add(question())
    preparation_id, session_id = start_session(client, user)

    ask(client, user, session_id)

    call = interviewer.calls[0]
    assert call.user_id == user.user_id
    assert str(call.preparation.id) == preparation_id
    assert call.preparation.job_title == JOB["job_title"]


def test_an_interview_that_is_over_answers_409_session_finished_and_stores_nothing(
    client: TestClient, user: "Credentials", interviewer: "FakeInterviewer"
):
    """When the engine says it is finished, the route reports why and adds no turn."""
    interviewer.add(InterviewFinished(reason=FinishedReason.QUESTION_COUNT_REACHED))
    _, session_id = start_session(client, user)

    response = ask(client, user, session_id)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "session_finished"
    assert error["details"] == {"reason": "question_count_reached"}
    stored = client.get(f"/v1/sessions/{session_id}", headers=user.headers).json()
    assert stored["turns"] == []


def test_a_session_at_the_turn_cap_is_finished_without_asking_the_model(
    client: TestClient,
    user: "Credentials",
    store: InMemorySessionStore,
    interviewer: "FakeInterviewer",
):
    """A session that already holds 100 questions answers 409 session_finished at once."""
    _, session_id = start_session(client, user)
    for _ in range(MAX_TURNS_PER_SESSION):
        turn = asyncio.run(store.add_question(user.user_id, UUID(session_id), question()))
        answer(store, user, session_id, str(turn.question.id))

    response = ask(client, user, session_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_finished"
    assert interviewer.calls == []


@pytest.mark.parametrize("ending", ["abandon", "complete"])
def test_a_session_that_has_ended_answers_409_invalid_state(
    client: TestClient,
    user: "Credentials",
    store: InMemorySessionStore,
    interviewer: "FakeInterviewer",
    ending: str,
):
    """Completed and abandoned sessions take no more questions, and the model is not asked."""
    _, session_id = start_session(client, user)
    turn = asyncio.run(store.add_question(user.user_id, UUID(session_id), question()))
    answer(store, user, session_id, str(turn.question.id))
    assert (
        client.post(f"/v1/sessions/{session_id}/{ending}", headers=user.headers).status_code == 200
    )

    response = ask(client, user, session_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"
    assert interviewer.calls == []


def test_an_abandoned_session_with_an_open_question_is_still_invalid_state(
    client: TestClient,
    user: "Credentials",
    store: InMemorySessionStore,
    interviewer: "FakeInterviewer",
):
    """The status check comes first: an abandoned session does not hand back its open question."""
    _, session_id = start_session(client, user)
    asyncio.run(store.add_question(user.user_id, UUID(session_id), question()))
    client.post(f"/v1/sessions/{session_id}/abandon", headers=user.headers)

    response = ask(client, user, session_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_an_unknown_session_and_another_users_session_are_both_404(
    client: TestClient,
    user: "Credentials",
    other_user: "Credentials",
    interviewer: "FakeInterviewer",
):
    """A session that is not yours looks exactly like one that does not exist."""
    _, session_id = start_session(client, user)

    foreign = ask(client, other_user, session_id)
    missing = ask(client, user, "00000000-0000-4000-8000-000000000000")

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert foreign.json()["error"]["code"] == "not_found"
    assert interviewer.calls == []


def test_two_simultaneous_requests_make_one_model_call_and_one_open_question(
    client: TestClient, user: "Credentials", interviewer: "FakeInterviewer"
):
    """Two requests at once: one asks the model (201), the other waits and gets that question (200)."""

    async def slow_question() -> Question:
        await asyncio.sleep(0.2)
        return question()

    interviewer.add(slow_question)
    _, session_id = start_session(client, user)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: ask(client, user, session_id), range(2)))

    assert sorted(response.status_code for response in results) == [200, 201]
    assert results[0].json()["question"]["id"] == results[1].json()["question"]["id"]
    assert len(interviewer.calls) == 1


def test_a_question_added_by_another_process_meanwhile_is_returned_instead(
    client: TestClient,
    user: "Credentials",
    store: InMemorySessionStore,
    interviewer: "FakeInterviewer",
):
    """If a second server process wins the race, this request returns the winner's question."""
    winner = question("The question another process stored first?")
    _, session_id = start_session(client, user)

    async def lose_the_race() -> Question:
        await store.add_question(user.user_id, UUID(session_id), winner)
        return question("The question this request wrote too late?")

    interviewer.add(lose_the_race)

    response = ask(client, user, session_id)

    assert response.status_code == 200
    assert response.json()["question"]["id"] == str(winner.id)
    stored = client.get(f"/v1/sessions/{session_id}", headers=user.headers).json()
    assert len(stored["turns"]) == 1


def test_a_model_error_maps_to_its_status_and_leaves_the_session_unchanged(
    client: TestClient, user: "Credentials", interviewer: "FakeInterviewer"
):
    """A failing model call becomes the shared error answer, and no turn is stored."""
    interviewer.add(LLMTimeoutError("The model did not answer in time."), question())
    _, session_id = start_session(client, user)

    failed = ask(client, user, session_id)

    assert failed.status_code == 504
    assert failed.json()["error"]["code"] == "llm_timeout"
    assert failed.json()["error"]["retryable"] is True
    assert client.get(f"/v1/sessions/{session_id}", headers=user.headers).json()["turns"] == []
    assert ask(client, user, session_id).status_code == 201


def test_the_route_documents_both_success_answers_and_its_errors(client: TestClient):
    """OpenAPI lists 200 and 201 with the Turn model, and the errors a client must handle."""
    operation = client.get("/openapi.json").json()["paths"]["/v1/sessions/{session_id}/turns"][
        "post"
    ]

    assert operation["summary"] == "Ask Next Question"
    for code in ("200", "201"):
        reference = operation["responses"][code]["content"]["application/json"]["schema"]["$ref"]
        # FastAPI calls the model `Turn-Output` when another route also takes a Turn as input.
        assert reference.rsplit("/", 1)[-1] in {"Turn", "Turn-Output"}
    for code in ("401", "404", "409", "422", "502", "504"):
        assert code in operation["responses"]
