import json
import logging

from api.main import create_app
from api.settings import ApiSettings
from contracts import Answer, Question
from fastapi.testclient import TestClient
from llm_gateway import Completion, ContextBudgetExceededError
from llm_gateway.testing import FakeLLM

QUESTION_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"


def _question() -> Question:
    """The question sent to the developer grading route."""
    return Question(
        id=QUESTION_ID,
        text="How does React decide when to re-render a component?",
        skill_id="react-rendering",
        difficulty=3,
    )


def _answer(transcript: str = "React re-renders when state or props change.") -> Answer:
    """The answer sent to the developer grading route."""
    return Answer(transcript=transcript, duration=20.0)


def _body(*, answer: Answer | None = None) -> dict:
    """A complete developer grading request."""
    return {
        "job_title": "Frontend Engineer",
        "question": _question().model_dump(mode="json"),
        "answer": (answer or _answer()).model_dump(mode="json"),
    }


def _reply() -> dict:
    """A complete grading reply."""
    data = {"summary": "Solid answer overall."}
    for metric in ("correctness", "depth", "clarity", "relevance"):
        data[metric] = {"score": 7, "feedback": "Reasonable."}
    return data


def _completion() -> Completion:
    """A successful fake grading completion with usage counts."""
    return Completion(
        text=json.dumps(_reply()),
        model="fake-model",
        prompt_tokens=400,
        completion_tokens=120,
    )


def build_app(llm: FakeLLM, *, dev_routes: bool = True):
    """Build the API with no environment reads and the developer route configurable."""
    settings = ApiSettings(_env_file=None, dev_routes=dev_routes)  # pyright: ignore[reportCallIssue]
    return create_app(settings=settings, llm=llm)


def test_grade_returns_the_evaluation_elapsed_time_and_tokens():
    """The route returns a validated evaluation with duration and provider usage."""
    fake = FakeLLM(_completion())
    with TestClient(build_app(fake)) as client:
        response = client.post("/v1/dev/grade", json=_body())

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation"]["question_id"] == QUESTION_ID
    assert body["evaluation"]["correctness"]["score"] == 7
    assert isinstance(body["elapsed_ms"], int)
    assert body["prompt_tokens"] == 400
    assert body["completion_tokens"] == 120
    assert len(fake.calls) == 1


def test_silence_returns_a_fixed_evaluation_without_a_model_call():
    """An empty transcript gets the zero-score evaluation and no token counts."""
    fake = FakeLLM()
    with TestClient(build_app(fake)) as client:
        response = client.post("/v1/dev/grade", json=_body(answer=_answer("   ")))

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation"]["correctness"]["score"] == 0
    assert body["prompt_tokens"] is None
    assert body["completion_tokens"] is None
    assert fake.calls == []


def test_unusable_grades_map_to_the_retryable_free_bad_response():
    """Two unusable replies map to 502 llm_bad_response with retryable false."""
    marker = "private-answer-marker"
    fake = FakeLLM(f"not JSON {marker}", f"still not JSON {marker}")
    with TestClient(build_app(fake)) as client:
        response = client.post("/v1/dev/grade", json=_body(answer=_answer(marker)))

    payload = response.json()["error"]
    assert response.status_code == 502
    assert payload["code"] == "llm_bad_response"
    assert payload["retryable"] is False
    assert marker not in response.text


def test_context_budget_errors_keep_the_shared_413_mapping():
    """A prompt that does not fit is the existing context_too_large error."""
    fake = FakeLLM(ContextBudgetExceededError("too long"))
    with TestClient(build_app(fake)) as client:
        response = client.post("/v1/dev/grade", json=_body())

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "context_too_large"


def test_unknown_fields_are_rejected_without_echoing_the_answer():
    """The request rejects unknown fields and the validation body hides the answer."""
    marker = "private-answer-marker"
    body = _body(answer=_answer(marker))
    body["unexpected"] = "value"
    with TestClient(build_app(FakeLLM("unused"))) as client:
        response = client.post("/v1/dev/grade", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert marker not in response.text


def test_logs_never_contain_the_answer_or_question(caplog):
    """Model-call logs record metadata only, never the graded text."""
    marker = "private-answer-marker"
    caplog.set_level(logging.INFO, logger="api.dev_evaluator")
    body = _body(answer=_answer(marker))

    with TestClient(build_app(FakeLLM(_completion()))) as client:
        response = client.post("/v1/dev/grade", json=body)

    assert response.status_code == 200
    assert "model_call outcome=ok model=fake-model" in caplog.text
    assert "dev_grade outcome=ok" in caplog.text
    assert marker not in caplog.text


def test_dev_grade_route_is_hidden_when_developer_routes_are_disabled():
    """The route is absent from routing and OpenAPI when developer routes are off."""
    with TestClient(build_app(FakeLLM("unused"), dev_routes=False)) as client:
        response = client.post("/v1/dev/grade", json=_body())
        schema = client.get("/openapi.json").json()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert "/v1/dev/grade" not in schema["paths"]


def test_openapi_documents_the_dev_grade_route_and_error_responses():
    """The route documents its purpose, output, and expected API error statuses."""
    with TestClient(build_app(FakeLLM("unused"))) as client:
        schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/v1/dev/grade"]["post"]
    assert operation["summary"] == "Grade one interview answer"
    assert operation["responses"]["200"]["description"] == (
        "The evaluation, the evaluator call duration, and provider token usage."
    )
    assert {"413", "422", "500", "502", "503", "504"}.issubset(operation["responses"])
