"""Tests for the turns route with the real question source and a scripted fake model.

Nothing is injected except the model, the stores and the clock, so these tests run the same
code path as the running API: lazy skill extraction, the engine and the end rule.
"""

import asyncio
import json
import logging
from collections.abc import Generator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from uuid import UUID

import pytest
from api.main import create_app
from api.settings import ApiSettings
from contracts import Answer
from fastapi.testclient import TestClient
from llm_gateway.interface import LLM
from llm_gateway.models import ChatMessage, Completion
from llm_gateway.testing import FakeLLM
from session_store import InMemorySessionStore
from skill_graph import InMemorySkillStore

JOB_MARKER = "job-text-marker-7f3a"
RESUME_MARKER = "resume-text-marker-91bc"
JOB = {
    "job_title": "Junior React Developer",
    "job_description": f"Build interfaces with React and TypeScript. {JOB_MARKER}",
    "resume": f"Built a task tracker with React. {RESUME_MARKER}",
}

# Five questions that differ enough for the engine's repeat check to accept all of them.
QUESTIONS = [
    "How would you decide between useState and useReducer in a component?",
    "What problem does the dependency array of useEffect solve?",
    "Why does Suspense need a boundary above the component that suspends?",
    "When would you reach for a context provider instead of passing props down?",
    "How do keys help React update a long list of items efficiently?",
]


class SlowLLM:
    """Wrap a model so every call pauses first, letting other requests run in the meantime."""

    def __init__(self, llm: FakeLLM) -> None:
        """Wrap the scripted model."""
        self._llm = llm

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ) -> Completion:
        """Pause briefly, then forward the call."""
        await asyncio.sleep(0.05)
        return await self._llm.complete(
            messages, temperature=temperature, max_output_tokens=max_output_tokens
        )


def extraction_reply() -> str:
    """A valid skill-extraction reply with three skills, one with an unusual label."""
    return json.dumps(
        {
            "categories": [
                {
                    "label": "React",
                    "skills": [
                        {"label": "hooks", "importance": 4, "difficulty": 2},
                        {"label": "suspense boundaries", "importance": 3, "difficulty": 3},
                        {"label": "state", "importance": 5, "difficulty": 3},
                    ],
                }
            ]
        }
    )


@contextmanager
def running_api(
    llm: LLM, store: InMemorySessionStore, skill_store: InMemorySkillStore
) -> Generator[TestClient]:
    """Start the API with only the model, the stores and the settings replaced."""
    settings = ApiSettings(_env_file=None)  # pyright: ignore[reportCallIssue]
    app = create_app(settings=settings, llm=llm, skill_store=skill_store, store=store)
    with TestClient(app) as client:
        yield client


def sign_up(client: TestClient) -> dict[str, str]:
    """Create an identity and return its Authorization header."""
    token = client.post("/v1/identity").json()["token"]
    return {"Authorization": f"Bearer {token}"}


def start_session(client: TestClient, headers: dict[str, str], preparation_id: str | None = None):
    """Create a preparation (unless one is given) and a session; return both ids."""
    if preparation_id is None:
        preparation_id = client.post("/v1/preparations", json=JOB, headers=headers).json()["id"]
    session = client.post(f"/v1/preparations/{preparation_id}/sessions", headers=headers)
    return preparation_id, session.json()["id"]


def ask(client: TestClient, headers: dict[str, str], session_id: str):
    """Call the route under test."""
    return client.post(f"/v1/sessions/{session_id}/turns", headers=headers)


def answer_in_store(
    store: InMemorySessionStore, user_id: UUID, session_id: str, question_id: str
) -> None:
    """Answer a question directly in the store, as the answer route will later do."""
    asyncio.run(
        store.record_answer(
            user_id,
            UUID(session_id),
            UUID(question_id),
            Answer(transcript="An answer.", duration=5.0),
        )
    )


def test_the_first_question_extracts_the_skills_for_the_signed_in_user(
    store: InMemorySessionStore, skill_store: InMemorySkillStore
):
    """Extraction is saved on the preparation, and learned labels belong to the user, not 'dev'."""
    llm = FakeLLM(extraction_reply(), QUESTIONS[0])
    with running_api(llm, store, skill_store) as client:
        identity = client.post("/v1/identity").json()
        headers = {"Authorization": f"Bearer {identity['token']}"}
        preparation_id, session_id = start_session(client, headers)

        response = ask(client, headers, session_id)

    assert response.status_code == 201
    assert response.json()["question"]["text"] == QUESTIONS[0]
    saved = asyncio.run(store.get_skill_graph(UUID(identity["user_id"]), UUID(preparation_id)))
    assert saved is not None
    owned = {
        e.node_label for e in asyncio.run(skill_store.catalog.all_entries(identity["user_id"]))
    }
    shared = {e.node_label for e in asyncio.run(skill_store.catalog.all_entries("dev"))}
    assert "suspense boundaries" in owned
    assert "suspense boundaries" not in shared


def test_later_questions_reuse_the_saved_skills_without_extracting_again(
    store: InMemorySessionStore, skill_store: InMemorySkillStore
):
    """The second question costs one model call: the graph was saved by the first."""
    llm = FakeLLM(extraction_reply(), QUESTIONS[0], QUESTIONS[1])
    with running_api(llm, store, skill_store) as client:
        identity = client.post("/v1/identity").json()
        headers = {"Authorization": f"Bearer {identity['token']}"}
        _, session_id = start_session(client, headers)
        first = ask(client, headers, session_id).json()
        answer_in_store(store, UUID(identity["user_id"]), session_id, first["question"]["id"])

        second = ask(client, headers, session_id)

    assert second.status_code == 201
    assert len(llm.calls) == 3


def test_two_simultaneous_first_turns_of_one_preparation_extract_the_skills_once(
    store: InMemorySessionStore, skill_store: InMemorySkillStore
):
    """Two sessions asking at once share one extraction: three model calls, not four."""
    llm = FakeLLM(extraction_reply(), QUESTIONS[0], QUESTIONS[1])
    with running_api(SlowLLM(llm), store, skill_store) as client:
        headers = sign_up(client)
        preparation_id, session_a = start_session(client, headers)
        _, session_b = start_session(client, headers, preparation_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(lambda sid: ask(client, headers, sid), [session_a, session_b])
            )

    assert [response.status_code for response in responses] == [201, 201]
    assert len(llm.calls) == 3


def test_the_interview_ends_after_the_configured_five_questions(
    store: InMemorySessionStore,
    skill_store: InMemorySkillStore,
    monkeypatch: pytest.MonkeyPatch,
):
    """With the question count set to five, the sixth request answers 409 and asks no model."""
    monkeypatch.setenv("ENGINE_DEFAULT_QUESTION_COUNT", "5")
    llm = FakeLLM(extraction_reply(), *QUESTIONS)
    with running_api(llm, store, skill_store) as client:
        identity = client.post("/v1/identity").json()
        headers = {"Authorization": f"Bearer {identity['token']}"}
        _, session_id = start_session(client, headers)
        for _ in QUESTIONS:
            turn = ask(client, headers, session_id)
            assert turn.status_code == 201
            answer_in_store(
                store, UUID(identity["user_id"]), session_id, turn.json()["question"]["id"]
            )

        sixth = ask(client, headers, session_id)

    assert sixth.status_code == 409
    error = sixth.json()["error"]
    assert error["code"] == "session_finished"
    assert error["details"] == {"reason": "question_count_reached"}
    assert len(llm.calls) == 1 + len(QUESTIONS)


def test_a_failed_extraction_answers_502_stores_nothing_and_a_retry_succeeds(
    store: InMemorySessionStore, skill_store: InMemorySkillStore
):
    """When the model cannot produce skills, the request fails cleanly and can simply be repeated."""
    llm = FakeLLM("not json", "still not json", extraction_reply(), QUESTIONS[0])
    with running_api(llm, store, skill_store) as client:
        headers = sign_up(client)
        _, session_id = start_session(client, headers)

        failed = ask(client, headers, session_id)
        stored = client.get(f"/v1/sessions/{session_id}", headers=headers).json()
        retry = ask(client, headers, session_id)

    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "llm_bad_response"
    assert stored["turns"] == []
    assert retry.status_code == 201


def test_neither_the_logs_nor_an_error_answer_contain_the_job_or_resume_text(
    store: InMemorySessionStore,
    skill_store: InMemorySkillStore,
    caplog: pytest.LogCaptureFixture,
):
    """Job description, resume and question text stay out of the log and out of error bodies."""
    caplog.set_level(logging.DEBUG)
    llm = FakeLLM("not json", "still not json", extraction_reply(), QUESTIONS[0])
    with running_api(llm, store, skill_store) as client:
        headers = sign_up(client)
        _, session_id = start_session(client, headers)

        failed = ask(client, headers, session_id)
        succeeded = ask(client, headers, session_id)

    for text in (caplog.text, failed.text):
        assert JOB_MARKER not in text
        assert RESUME_MARKER not in text
    assert QUESTIONS[0] not in caplog.text
    assert succeeded.status_code == 201
