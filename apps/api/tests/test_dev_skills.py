import json
import logging

from api.dependencies import get_llm, get_skill_catalog
from api.main import create_app
from api.settings import ApiSettings
from fastapi.testclient import TestClient
from llm_gateway import Completion, ContextBudgetExceededError
from llm_gateway.testing import FakeLLM
from skill_graph import InMemorySkillCatalog


def valid_reply() -> dict[str, object]:
    """Return a nested reply with three technical skills for route tests."""
    return {
        "categories": [
            {
                "label": "React",
                "skills": [
                    {"label": "hooks", "importance": 4, "difficulty": 2},
                    {"label": "routing", "importance": 3, "difficulty": 3},
                    {"label": "state", "importance": 5, "difficulty": 3},
                ],
            }
        ]
    }


def build_app(llm: FakeLLM, *, dev_routes: bool = True):
    """Build the API with model settings disabled and test routes configurable."""
    settings = ApiSettings(_env_file=None, dev_routes=dev_routes)  # pyright: ignore[reportCallIssue]
    return create_app(settings=settings, llm=llm)


def test_extract_skills_returns_the_graph_and_elapsed_time():
    """The developer route returns the validated graph and elapsed milliseconds."""
    fake = FakeLLM(Completion(text=json.dumps(valid_reply()), model="fake-model"))
    app = build_app(fake)

    with TestClient(app) as client:
        response = client.post(
            "/v1/dev/extract-skills",
            json={
                "job_title": "React Developer",
                "job_description": "Build accessible web interfaces.",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["graph"]["nodes"]) == 4
    assert isinstance(body["elapsed_ms"], int)
    assert body["elapsed_ms"] >= 0
    assert len(fake.calls) == 1


def test_extract_skills_uses_dependency_overrides_for_model_and_catalog():
    """Tests can replace both external model calls and catalog storage through dependencies."""
    original = FakeLLM("unused")
    replacement = FakeLLM(Completion(text=json.dumps(valid_reply()), model="fake-model"))
    catalog = InMemorySkillCatalog(seed_entries=())
    app = build_app(original)
    app.dependency_overrides[get_llm] = lambda: replacement
    app.dependency_overrides[get_skill_catalog] = lambda: catalog

    with TestClient(app) as client:
        response = client.post(
            "/v1/dev/extract-skills",
            json={"job_title": "React Developer", "job_description": "Build interfaces."},
        )

    assert response.status_code == 200
    assert original.calls == []
    assert len(replacement.calls) == 1


def test_extract_skills_rejects_unknown_fields_and_does_not_echo_job_text():
    """The request rejects unknown fields and the shared validation envelope hides user text."""
    marker = "private-job-description-marker"
    with TestClient(build_app(FakeLLM("unused"))) as client:
        response = client.post(
            "/v1/dev/extract-skills",
            json={
                "job_title": "Developer",
                "job_description": marker,
                "resume": "not accepted",
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert marker not in response.text


def test_extract_skills_passes_a_context_budget_error_through_the_shared_handler():
    """A prompt budget failure uses the existing context_too_large API error mapping."""
    with TestClient(build_app(FakeLLM(ContextBudgetExceededError("too long")))) as client:
        response = client.post(
            "/v1/dev/extract-skills",
            json={"job_title": "Developer", "job_description": "Build software."},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "context_too_large"


def test_extract_skills_returns_a_safe_error_after_repair_is_exhausted():
    """A model reply that remains unusable maps to the established bad-response code."""
    marker = "private model reply"
    with TestClient(build_app(FakeLLM(marker, marker))) as client:
        response = client.post(
            "/v1/dev/extract-skills",
            json={"job_title": "Developer", "job_description": "Build software."},
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "llm_bad_response"
    assert response.json()["error"]["message"] == "The model could not produce a valid skill graph."
    assert marker not in response.text


def test_extract_skills_logs_model_metadata_without_job_content(caplog):
    """Model-call logs include outcome metadata but never the pasted job description."""
    marker = "private-job-description-marker"
    caplog.set_level(logging.INFO, logger="api.dev_skills")
    fake = FakeLLM(Completion(text=json.dumps(valid_reply()), model="fake-model"))

    with TestClient(build_app(fake)) as client:
        response = client.post(
            "/v1/dev/extract-skills",
            json={"job_title": "Developer", "job_description": marker},
        )

    assert response.status_code == 200
    assert "model_call outcome=ok model=fake-model" in caplog.text
    assert marker not in caplog.text


def test_dev_skill_route_is_hidden_when_developer_routes_are_disabled():
    """The extraction endpoint is absent from routing and OpenAPI when dev routes are off."""
    with TestClient(build_app(FakeLLM("unused"), dev_routes=False)) as client:
        response = client.post(
            "/v1/dev/extract-skills",
            json={"job_title": "Developer", "job_description": "Build software."},
        )
        schema = client.get("/openapi.json").json()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert "/v1/dev/extract-skills" not in schema["paths"]


def test_openapi_documents_the_dev_skill_route_and_error_responses():
    """The route documents its purpose, output, and expected API error statuses."""
    with TestClient(build_app(FakeLLM("unused"))) as client:
        schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/v1/dev/extract-skills"]["post"]
    assert operation["summary"] == "Extract a job's technical skill graph"
    assert operation["responses"]["200"]["description"] == (
        "The validated skill graph and extraction time."
    )
    assert {"413", "422", "500", "502", "503", "504"}.issubset(operation["responses"])


RAW_PATH = "/v1/dev/extract-skills/raw?job_title=Junior%20React%20Developer"
PLAIN_TEXT = {"Content-Type": "text/plain; charset=utf-8"}


def test_raw_skill_extraction_accepts_a_multiline_plain_text_body():
    """A pasted job description with real line breaks needs no JSON escaping."""
    fake = FakeLLM(Completion(text=json.dumps(valid_reply()), model="fake-model"))
    description = "About the job\nBuild accessible React interfaces.\nWork with hooks."
    with TestClient(build_app(fake)) as client:
        response = client.post(RAW_PATH, content=description, headers=PLAIN_TEXT)

    assert response.status_code == 200
    body = response.json()
    assert len(body["graph"]["nodes"]) == 4
    assert isinstance(body["elapsed_ms"], int)
    assert len(fake.calls) == 1


def test_raw_skill_extraction_rejects_a_blank_body_without_calling_the_model():
    """A body that is only whitespace is an invalid request, not a wasted model call."""
    fake = FakeLLM("unused")
    with TestClient(build_app(fake)) as client:
        response = client.post(RAW_PATH, content="  \n\t  ", headers=PLAIN_TEXT)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert fake.calls == []


def test_raw_skill_extraction_rejects_an_oversized_body_without_echoing_it():
    """The same description limit as the JSON route applies, and the body is not returned."""
    marker = "private-description-marker"
    body = marker + "x" * 20_000
    with TestClient(build_app(FakeLLM("unused"))) as client:
        response = client.post(RAW_PATH, content=body, headers=PLAIN_TEXT)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert marker not in response.text


def test_raw_skill_extraction_requires_a_job_title():
    """The title is a required query parameter, so a body alone cannot start extraction."""
    with TestClient(build_app(FakeLLM("unused"))) as client:
        response = client.post(
            "/v1/dev/extract-skills/raw",
            content="Build React interfaces.",
            headers=PLAIN_TEXT,
        )

    assert response.status_code == 422


def test_raw_skill_route_is_hidden_when_developer_routes_are_disabled():
    """The plain-text route disappears from routing and OpenAPI with the other dev routes."""
    with TestClient(build_app(FakeLLM("unused"), dev_routes=False)) as client:
        response = client.post(RAW_PATH, content="Build React interfaces.", headers=PLAIN_TEXT)
        schema = client.get("/openapi.json").json()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert "/v1/dev/extract-skills/raw" not in schema["paths"]


def test_raw_skill_logs_never_contain_the_pasted_description(caplog):
    """The plain-text route follows the same metadata-only logging rule."""
    marker = "private-description-marker"
    caplog.set_level(logging.INFO, logger="api.dev_skills")
    fake = FakeLLM(Completion(text=json.dumps(valid_reply()), model="fake-model"))

    with TestClient(build_app(fake)) as client:
        response = client.post(
            RAW_PATH,
            content=f"About the job\n{marker}",
            headers=PLAIN_TEXT,
        )

    assert response.status_code == 200
    assert "model_call outcome=ok model=fake-model" in caplog.text
    assert marker not in caplog.text


def test_openapi_documents_the_raw_route_query_and_plain_text_body():
    """The raw route documents its title parameter, text/plain body, and error statuses."""
    with TestClient(build_app(FakeLLM("unused"))) as client:
        schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/v1/dev/extract-skills/raw"]["post"]
    assert operation["summary"] == "Extract a job's technical skill graph from plain text"
    assert operation["responses"]["200"]["description"] == (
        "The validated skill graph and extraction time."
    )
    assert "text/plain" in operation["requestBody"]["content"]
    title = next(item for item in operation["parameters"] if item["name"] == "job_title")
    assert title["required"] is True
    assert {"413", "422", "500", "502", "503", "504"}.issubset(operation["responses"])
