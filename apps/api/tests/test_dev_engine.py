import logging

from api.main import create_app
from api.settings import ApiSettings
from contracts import Question, SkillGraph, SkillNode, Turn, skill_id
from fastapi.testclient import TestClient
from llm_gateway import ContextBudgetExceededError
from llm_gateway.testing import FakeLLM

ROOT = "React"


def _graph() -> SkillGraph:
    """A React root with three leaves for the developer request."""
    root = SkillNode(
        id=skill_id(ROOT, ROOT),
        label=ROOT,
        parent_id=None,
        importance=None,
        difficulty=None,
    )
    leaves = [
        SkillNode(
            id=skill_id(ROOT, label),
            label=label,
            parent_id=root.id,
            importance=4,
            difficulty=3,
        )
        for label in ("Hooks", "State", "Effects")
    ]
    return SkillGraph(nodes=(root, *leaves))


def _body(*, turns=(), earlier=(), config=None) -> dict:
    """A complete developer request with overridable turns, earlier questions, and enums."""
    return {
        "job_title": "Frontend Engineer",
        "job_description": "Build accessible interfaces with React and TypeScript.",
        "skill_graph": _graph().model_dump(mode="json"),
        "turns": [turn.model_dump(mode="json") for turn in turns],
        "earlier_questions": [question.model_dump(mode="json") for question in earlier],
        "interview_config": config or {"rule": "question_count", "count": 1},
    }


def build_app(llm: FakeLLM, *, dev_routes: bool = True):
    """Build the API with no environment reads and the developer route configurable."""
    settings = ApiSettings(_env_file=None, dev_routes=dev_routes)  # pyright: ignore[reportCallIssue]
    return create_app(settings=settings, llm=llm)


def test_next_question_returns_a_question_and_elapsed_time():
    """The developer route returns the question and how long the engine took."""
    fake = FakeLLM("How does React batch state updates?")
    with TestClient(build_app(fake)) as client:
        response = client.post("/v1/dev/next-question", json=_body())

    assert response.status_code == 200
    body = response.json()
    assert body["question"]["text"] == "How does React batch state updates?"
    assert body["question"]["difficulty"] == 2
    assert body["finished"] is None
    assert isinstance(body["elapsed_ms"], int)
    assert body["elapsed_ms"] >= 0
    assert len(fake.calls) == 1


def test_next_question_returns_the_finished_reason_and_no_model_call():
    """A reached end rule is returned as the finished result with no model call."""
    turn = Turn(
        question=Question(text="Explain hooks.", skill_id=skill_id(ROOT, "Hooks"), difficulty=2)
    )
    fake = FakeLLM()
    with TestClient(build_app(fake)) as client:
        response = client.post("/v1/dev/next-question", json=_body(turns=[turn]))

    assert response.status_code == 200
    body = response.json()
    assert body["question"] is None
    assert body["finished"]["reason"] == "question_count_reached"
    assert fake.calls == []


def test_unusable_question_maps_to_the_retryable_bad_response_code():
    """A model that cannot write a usable question maps to 502 llm_bad_response and is retryable."""
    marker = "private model reply"
    fake = FakeLLM(f"{marker} `code`?", "x" * 301)
    with TestClient(build_app(fake)) as client:
        response = client.post("/v1/dev/next-question", json=_body())

    payload = response.json()["error"]
    assert response.status_code == 502
    assert payload["code"] == "llm_bad_response"
    assert payload["retryable"] is True
    assert marker not in response.text


def test_context_budget_error_keeps_the_shared_413_mapping():
    """A prompt that does not fit the model context is the existing context_too_large error."""
    fake = FakeLLM(ContextBudgetExceededError("too long"))
    with TestClient(build_app(fake)) as client:
        response = client.post("/v1/dev/next-question", json=_body())

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "context_too_large"


def test_unknown_fields_are_rejected_without_echoing_the_job_text():
    """The request rejects unknown fields and the error body hides the pasted content."""
    marker = "private-job-description-marker"
    body = _body()
    body["job_description"] = marker
    body["unexpected"] = "value"
    with TestClient(build_app(FakeLLM("unused"))) as client:
        response = client.post("/v1/dev/next-question", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert marker not in response.text


def test_logs_never_contain_the_job_description(caplog):
    """Model and route logs record metadata only, never pasted job text."""
    marker = "private-job-description-marker"
    caplog.set_level(logging.INFO, logger="api.dev_engine")
    body = _body()
    body["job_description"] = marker

    with TestClient(build_app(FakeLLM("How does React batch state updates?"))) as client:
        response = client.post("/v1/dev/next-question", json=body)

    assert response.status_code == 200
    assert "model_call outcome=ok model=fake-model" in caplog.text
    assert "dev_engine outcome=question" in caplog.text
    assert marker not in caplog.text


def test_dev_engine_route_is_hidden_when_developer_routes_are_disabled():
    """The route is absent from routing and OpenAPI when developer routes are off."""
    with TestClient(build_app(FakeLLM("unused"), dev_routes=False)) as client:
        response = client.post("/v1/dev/next-question", json=_body())
        schema = client.get("/openapi.json").json()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert "/v1/dev/next-question" not in schema["paths"]


def test_openapi_documents_the_dev_engine_route_and_error_responses():
    """The route documents its purpose, output, and expected API error statuses."""
    with TestClient(build_app(FakeLLM("unused"))) as client:
        schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/v1/dev/next-question"]["post"]
    assert operation["summary"] == "Ask the engine for the next question"
    assert operation["responses"]["200"]["description"] == (
        "The next question or the finished reason, with elapsed time."
    )
    assert {"413", "422", "500", "502", "503", "504"}.issubset(operation["responses"])
