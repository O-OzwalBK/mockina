"""Tests for the deadline on POST /v1/sessions/{id}/turns, with a very short limit."""

import asyncio
from typing import TYPE_CHECKING

import pytest
from api.settings import ApiSettings
from contracts import Question, skill_id
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from conftest import Credentials, FakeInterviewer


@pytest.fixture
def api_settings() -> ApiSettings:
    """API settings whose question deadline is 50 milliseconds, so a test need not wait."""
    return ApiSettings(_env_file=None, turn_timeout_seconds=0.05)  # pyright: ignore[reportCallIssue]


def a_question() -> Question:
    """A valid question, with a skill id made the way production makes them."""
    return Question(
        text="How do React hooks work?", skill_id=skill_id("React", "hooks"), difficulty=2
    )


def test_a_question_slower_than_the_deadline_answers_504_and_can_be_retried(
    client: TestClient, user: "Credentials", interviewer: "FakeInterviewer"
):
    """Past `turn_timeout_seconds` the route answers a retryable 504 and stores nothing."""

    async def too_slow() -> Question:
        await asyncio.sleep(5)
        return a_question()

    interviewer.add(too_slow, a_question())
    preparation = client.post(
        "/v1/preparations",
        json={"job_title": "Junior React Developer", "job_description": "Build with React."},
        headers=user.headers,
    ).json()
    session = client.post(
        f"/v1/preparations/{preparation['id']}/sessions", headers=user.headers
    ).json()
    url = f"/v1/sessions/{session['id']}/turns"

    slow = client.post(url, headers=user.headers)
    stored = client.get(f"/v1/sessions/{session['id']}", headers=user.headers).json()
    retry = client.post(url, headers=user.headers)

    assert slow.status_code == 504
    error = slow.json()["error"]
    assert error["code"] == "llm_timeout"
    assert error["retryable"] is True
    assert stored["turns"] == []
    assert retry.status_code == 201
