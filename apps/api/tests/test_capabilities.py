"""Tests for GET /v1/capabilities: what this server offers and the limits it enforces."""

import pytest
from api.main import create_app
from api.product_models import Limits
from api.settings import ApiSettings
from contracts.preparation import (
    MAX_JOB_DESCRIPTION_LENGTH,
    MAX_JOB_TITLE_LENGTH,
    MAX_RESUME_LENGTH,
)
from contracts.transcript import (
    MAX_ANSWER_DURATION_SECONDS,
    MAX_TRANSCRIPT_LENGTH,
    MAX_WORD_LENGTH,
    MAX_WORDS_PER_ANSWER,
)
from fastapi.testclient import TestClient
from llm_gateway.testing import FakeLLM
from session_store import InMemorySessionStore

# Each response limit and the contract constant it must equal.
LIMIT_SOURCES = {
    "max_job_title_length": MAX_JOB_TITLE_LENGTH,
    "max_job_description_length": MAX_JOB_DESCRIPTION_LENGTH,
    "max_resume_length": MAX_RESUME_LENGTH,
    "max_transcript_length": MAX_TRANSCRIPT_LENGTH,
    "max_words_per_answer": MAX_WORDS_PER_ANSWER,
    "max_word_length": MAX_WORD_LENGTH,
    "max_answer_seconds": MAX_ANSWER_DURATION_SECONDS,
}


def test_capabilities_need_no_token_and_have_the_documented_shape(client: TestClient):
    """The public route answers 200 with retention, hosted STT, dev routes and limits."""
    response = client.get("/v1/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"anonymous_retention_days", "hosted_stt", "dev_routes", "limits"}
    assert body["hosted_stt"] is False


def test_the_limit_list_is_not_empty():
    """Guard: the parametrized limit check below must always have cases."""
    assert LIMIT_SOURCES


@pytest.mark.parametrize(("name", "constant"), LIMIT_SOURCES.items())
def test_each_limit_equals_its_contract_constant(client: TestClient, name: str, constant: int):
    """A limit shown to the browser always equals the constant the contracts enforce."""
    limits = client.get("/v1/capabilities").json()["limits"]

    assert limits[name] == constant


def test_every_limit_field_has_a_source_constant():
    """Adding a field to Limits forces adding it to LIMIT_SOURCES, so it gets checked too."""
    assert set(Limits.model_fields) == set(LIMIT_SOURCES)


def test_retention_and_dev_routes_come_from_the_settings(store: InMemorySessionStore):
    """The advertised retention and developer-routes flag follow the API's own settings."""
    settings = ApiSettings(  # pyright: ignore[reportCallIssue]
        _env_file=None, anon_retention_days=7, dev_routes=True
    )
    app = create_app(settings=settings, llm=FakeLLM(), store=store)

    with TestClient(app) as client:
        body = client.get("/v1/capabilities").json()

    assert body["anonymous_retention_days"] == 7
    assert body["dev_routes"] is True


def test_capabilities_default_to_thirty_days_and_no_dev_routes(client: TestClient):
    """With default settings the server advertises 30 days and no developer routes."""
    body = client.get("/v1/capabilities").json()

    assert body["anonymous_retention_days"] == 30
    assert body["dev_routes"] is False


def test_openapi_describes_the_capabilities_response(client: TestClient):
    """The route has a summary, a response description and the Capabilities model."""
    operation = client.get("/openapi.json").json()["paths"]["/v1/capabilities"]["get"]

    assert operation["summary"]
    assert operation["responses"]["200"]["description"]
    reference = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert reference.endswith("/Capabilities")


def test_zero_retention_is_advertised_as_zero(store: InMemorySessionStore):
    """A server that never purges reports 0, as the agreed Capabilities shape allows."""
    settings = ApiSettings(_env_file=None, anon_retention_days=0)  # pyright: ignore[reportCallIssue]
    app = create_app(settings=settings, llm=FakeLLM(), store=store)

    with TestClient(app) as client:
        body = client.get("/v1/capabilities").json()

    assert body["anonymous_retention_days"] == 0
