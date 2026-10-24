import logging

import pytest
from api.main import LLM_ERROR_MAP, create_app, get_llm
from api.models import MAX_MESSAGE_CHARS
from api.settings import ApiSettings
from engine import UnusableQuestionError
from evaluator import EvaluationError
from fastapi.testclient import TestClient
from llm_gateway import (
    ContextBudgetExceededError,
    LLMAuthError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMServerError,
    LLMSettings,
    LLMTimeoutError,
)
from llm_gateway.models import ChatMessage, Completion
from llm_gateway.testing import FakeLLM
from pydantic import ValidationError


def test_health_route_does_not_need_the_model():
    """GET /health is healthy even when the model is only a test double."""

    llm = FakeLLM()
    app = create_app(settings=ApiSettings(_env_file=None), llm=llm)  # pyright: ignore[reportCallIssue]
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert llm.calls == []


def build_app(llm: FakeLLM, *, dev_routes: bool = True):
    """Build an API with no environment reads and the developer routes enabled by default."""

    settings = ApiSettings(_env_file=None, dev_routes=dev_routes)  # pyright: ignore[reportCallIssue]
    return create_app(settings=settings, llm=llm)


def test_complete_passes_through_messages_and_options():
    """The completion route forwards caller messages and generation options unchanged."""
    llm = FakeLLM(
        Completion(
            text="Hello!",
            model="test-model",
            finish_reason="stop",
            prompt_tokens=78,
            completion_tokens=87,
        )
    )
    app = build_app(llm)
    request = {
        "messages": [{"role": "user", "content": "Say hello."}],
        "temperature": 0.7,
        "max_output_tokens": 40,
    }

    with TestClient(app) as client:
        response = client.post("/v1/dev/complete", json=request)

    assert response.status_code == 200
    assert response.json()["text"] == "Hello!"
    assert response.json()["model"] == "test-model"
    assert response.json()["finish_reason"] == "stop"
    assert response.json()["prompt_tokens"] == 78
    assert response.json()["completion_tokens"] == 87
    assert isinstance(response.json()["elapsed_ms"], int)
    assert llm.calls[0].messages == (ChatMessage(role="user", content="Say hello."),)
    assert llm.calls[0].temperature == 0.7
    assert llm.calls[0].max_output_tokens == 40


def test_completion_uses_dependency_override():
    """A test can replace get_llm without changing the app's production wiring."""
    original = FakeLLM("unused")
    replacement = FakeLLM("from override")
    app = build_app(original)
    app.dependency_overrides[get_llm] = lambda: replacement

    with TestClient(app) as client:
        response = client.post(
            "/v1/dev/complete",
            json={"messages": [{"role": "user", "content": "test"}]},
        )

    assert response.status_code == 200
    assert response.json()["text"] == "from override"
    assert original.calls == []
    assert len(replacement.calls) == 1


def test_invalid_completion_body_uses_the_shared_error_shape():
    """Invalid request bodies return the standard envelope without echoing message text."""
    marker = "private-prompt-marker"
    with TestClient(build_app(FakeLLM("unused"))) as client:
        response = client.post(
            "/v1/dev/complete",
            json={
                "messages": [{"role": "user", "content": marker}],
                "temperature": 9,
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.json()["error"]["retryable"] is False
    assert marker not in response.text


def test_oversized_message_is_rejected_without_echoing_it():
    """The named per-message size limit rejects oversized content without returning it."""
    marker = "x" * (MAX_MESSAGE_CHARS + 1)
    with TestClient(build_app(FakeLLM("unused"))) as client:
        response = client.post(
            "/v1/dev/complete",
            json={"messages": [{"role": "user", "content": marker}]},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert marker not in response.text


ERROR_CASES = [
    (
        ContextBudgetExceededError("too long", estimated_tokens=20, budget_tokens=10),
        413,
        "context_too_large",
    ),
    (LLMRateLimitError("busy", retry_after=2.5), 503, "llm_rate_limited"),
    (LLMTimeoutError("timed out"), 504, "llm_timeout"),
    (LLMConnectionError("unreachable"), 502, "llm_unreachable"),
    (LLMServerError("server error"), 502, "llm_server_error"),
    (LLMResponseError("bad response"), 502, "llm_bad_response"),
    (
        UnusableQuestionError(
            "The model did not produce a usable question.",
            failures=("too_long",),
            attempts=2,
        ),
        502,
        "llm_bad_response",
    ),
    (
        EvaluationError(
            "The model did not produce a usable evaluation.",
            failures=("invalid_score",),
            attempts=2,
        ),
        502,
        "llm_bad_response",
    ),
    (LLMAuthError("bad provider key"), 502, "llm_auth_failed"),
    (LLMRequestError("provider rejected request"), 502, "llm_rejected_request"),
]


def test_error_case_list_is_not_empty():
    """Guard: the parametrized LLM error checks must always have cases."""
    assert ERROR_CASES


@pytest.mark.parametrize(("error", "status", "code"), ERROR_CASES)
def test_llm_errors_use_the_shared_error_mapping(
    error, status, code, caplog: pytest.LogCaptureFixture
):
    """Every gateway error maps to its documented HTTP status and stable code."""
    caplog.set_level(logging.INFO, logger="api.main")
    with TestClient(build_app(FakeLLM(error))) as client:
        response = client.post(
            "/v1/dev/complete",
            json={"messages": [{"role": "user", "content": "test"}]},
        )

    payload = response.json()["error"]
    assert response.status_code == status
    assert payload["code"] == code
    assert payload["message"] == str(error)
    assert payload["retryable"] is error.retryable
    assert f"outcome={type(error).__name__}" in caplog.text
    assert "prompt_tokens=unknown" in caplog.text
    assert "completion_tokens=unknown" in caplog.text
    if isinstance(error, ContextBudgetExceededError):
        assert payload["details"] == {"estimated_tokens": 20, "budget_tokens": 10}


def test_every_exported_llm_error_has_a_mapping():
    """Every concrete error exported by llm_gateway has an HTTP mapping."""
    exported_errors = set(LLMError.__subclasses__())
    assert exported_errors
    assert exported_errors == set(LLM_ERROR_MAP)


@pytest.mark.parametrize(
    ("retry_after", "header"), [(2.5, "3"), (30.0, "30"), (0.2, "1"), (0.0, "0")]
)
def test_rate_limit_retry_after_is_whole_seconds_rounded_up(retry_after, header):
    """An upstream retry delay is passed back in the Retry-After header and is rounded up before sending as whole seconds, so a client never retries too early."""

    error = LLMRateLimitError("busy", retry_after=retry_after)
    with TestClient(build_app(FakeLLM(error))) as client:
        response = client.post(
            "/v1/dev/complete",
            json={"messages": [{"role": "user", "content": "test"}]},
        )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == header


def test_rate_limit_without_the_provider_sending_delay_sends_no_retry_after_header_to_client():
    """When the provider gave no delay, the response has no Retry-After header at all."""

    with TestClient(build_app(FakeLLM(LLMRateLimitError("busy")))) as client:
        response = client.post(
            "/v1/dev/complete",
            json={"messages": [{"role": "user", "content": "test"}]},
        )

    assert response.status_code == 503
    assert "Retry-After" not in response.headers


def test_cors_preflight_allows_configured_origin():
    """CORS preflight allows the configured local browser origin and POST content type."""
    with TestClient(build_app(FakeLLM("unused"))) as client:
        response = client.options(
            "/v1/dev/complete",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-credentials" not in response.headers


def test_cors_preflight_rejects_unconfigured_origin():
    """CORS preflight does not grant an origin absent from API_CORS_ORIGINS."""
    with TestClient(build_app(FakeLLM("unused"))) as client:
        response = client.options(
            "/v1/dev/complete",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_dev_routes_are_absent_when_disabled_and_uses_the_shared_error():
    """Disabling developer routes removes them from both routing and gives the shared 404 error."""

    with TestClient(build_app(FakeLLM("unused"), dev_routes=False)) as client:
        response = client.post(
            "/v1/dev/complete",
            json={"messages": [{"role": "user", "content": "test"}]},
        )
        schema = client.get("/openapi.json").json()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert "/v1/dev/complete" not in schema["paths"]
    assert "/v1/dev/model" not in schema["paths"]


def test_unknown_path_uses_shared_error_shape():
    """An unknown path gets the shared 404 error envelope, not FastAPI's {"detail": ...}."""

    with TestClient(build_app(FakeLLM())) as client:
        response = client.get("/no-such-route")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Not Found",
            "retryable": False,
            "details": {},
        }
    }


def test_wrong_method_uses_shared_error_shape_and_keeps_the_allow_header():
    """A wrong method on a route that exists returns the shared 405 envelope and preserves Allow."""

    with TestClient(build_app(FakeLLM())) as client:
        response = client.get("/v1/dev/complete")

    assert response.status_code == 405
    assert response.headers["Allow"] == "POST"
    assert response.json() == {
        "error": {
            "code": "method_not_allowed",
            "message": "Method Not Allowed",
            "retryable": False,
            "details": {},
        }
    }


def test_model_info_reports_host_and_limits_without_the_key(monkeypatch: pytest.MonkeyPatch):
    """Model info exposes non-secret endpoint details and only whether a key is set."""
    key_marker = "private-key-marker"
    llm_settings = LLMSettings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        base_url="https://local-user:local-pass@api.groq.com/openai/v1",
        model="openai/gpt-oss-20b",
        api_key=key_marker,
        context_tokens=8192,
        max_output_tokens=1024,
        max_retries=0,
    )
    monkeypatch.setattr("api.main.LLMSettings", lambda: llm_settings)
    app = create_app(settings=ApiSettings(_env_file=None, dev_routes=True))  # pyright: ignore[reportCallIssue]

    with TestClient(app) as client:
        response = client.get("/v1/dev/model")

    assert response.status_code == 200
    assert response.json() == {
        "model": "openai/gpt-oss-20b",
        "host": "api.groq.com",
        "context_tokens": 8192,
        "max_output_tokens": 1024,
        "api_key_set": True,
    }
    assert key_marker not in response.text
    assert "local-user" not in response.text
    assert "local-pass" not in response.text


def test_openapi_documents_dev_routes_and_error_responses():
    """OpenAPI documents the developer route summary and every mapped error status."""
    with TestClient(build_app(FakeLLM("unused"))) as client:
        schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/v1/dev/complete"]["post"]
    assert operation["summary"] == "Complete a model conversation"
    assert operation["responses"]["200"]["description"] == (
        "The model reply and provider-reported usage."
    )
    assert {"413", "422", "500", "502", "503", "504"}.issubset(operation["responses"])


def test_model_call_log_does_not_contain_prompt_or_key(caplog: pytest.LogCaptureFixture):
    """The model-call log records outcome metadata without prompt or key values."""

    prompt_marker = "private-prompt-marker"
    key_marker = "private-key-marker"
    caplog.set_level(logging.INFO, logger="api.main")
    app = build_app(FakeLLM("safe reply"))

    with TestClient(app) as client:
        response = client.post(
            "/v1/dev/complete",
            json={"messages": [{"role": "user", "content": prompt_marker}]},
        )

    assert response.status_code == 200
    assert "outcome=ok" in caplog.text
    assert prompt_marker not in caplog.text
    assert key_marker not in caplog.text


def test_unexpected_error_is_generic_and_does_not_log_exception_text(
    caplog: pytest.LogCaptureFixture,
):
    """Unexpected failures return a generic body and redact exception text from logs."""

    marker = "private-prompt-marker"
    caplog.set_level(logging.ERROR, logger="api.main")

    with TestClient(
        build_app(FakeLLM(ValueError(marker))), raise_server_exceptions=False
    ) as client:
        response = client.post(
            "/v1/dev/complete",
            headers={"Origin": "http://localhost:5173"},
            json={"messages": [{"role": "user", "content": marker}]},
        )

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.json()["error"]["code"] == "internal_error"
    assert marker not in response.text
    assert marker not in caplog.text


def test_bad_llm_settings_fail_startup_without_logging_values(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Invalid model settings fail startup while diagnostics show names, not values."""

    with pytest.raises(ValidationError) as captured:
        LLMSettings(_env_file=None, base_url="not-a-url", model="test-model")  # pyright: ignore[reportCallIssue]
    settings_error = captured.value

    def fail_to_load_settings():
        raise settings_error

    monkeypatch.setattr("api.main.LLMSettings", fail_to_load_settings)
    caplog.set_level(logging.CRITICAL, logger="api.main")
    app = create_app(settings=ApiSettings(_env_file=None, dev_routes=True))  # pyright: ignore[reportCallIssue]

    with pytest.raises(RuntimeError) as startup_error, TestClient(app):
        pass

    assert "LLM_BASE_URL" in caplog.text
    assert "not-a-url" not in caplog.text
    assert "not-a-url" not in str(startup_error.value)
    assert "the API cannot start" in str(startup_error.value)


def test_openapi_describes_the_model_info_503_as_missing_configuration():
    """The model-info 503 is documented as 'no model settings', not as an upstream rate limit."""

    with TestClient(build_app(FakeLLM("unused"))) as client:
        schema = client.get("/openapi.json").json()

    description = schema["paths"]["/v1/dev/model"]["get"]["responses"]["503"]["description"]
    assert "settings" in description
    assert "rate limit" not in description
