import json
from typing import Any

import httpx2
import pytest
from llm_gateway import (
    LLM,
    ChatMessage,
    Completion,
    ContextBudgetExceededError,
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMServerError,
    LLMSettings,
    LLMTimeoutError,
    OpenAICompatibleLLM,
)
from llm_gateway.client import (
    build_request_body,
    parse_completion,
    parse_retry_after,
    raise_for_error_status,
)
from llm_gateway.errors import LLMError

MESSAGES = [
    ChatMessage(role="system", content="You are a strict interviewer."),
    ChatMessage(role="user", content="Grade this answer."),
]


# @pytest.fixture
# def anyio_backend():
#     """Run the async tests on asyncio only."""
#     return "asyncio"


def make_settings(**overrides: Any) -> LLMSettings:
    """Build settings that do not depend on the real environment or any .env file."""
    values: dict[str, Any] = {
        "base_url": "http://models.test/v1",
        "model": "test-model",
        "api_key": None,
        "context_tokens": 8192,
        "max_output_tokens": 1024,
        "timeout_seconds": 30.0,
        "max_retries": 0,
    }
    values.update(overrides)
    return LLMSettings(_env_file=None, **values)  # pyright: ignore[reportCallIssue]


def good_reply(text: str = "Hello there.") -> dict[str, Any]:
    """A reply in the shape OpenAI-compatible servers send."""
    return {
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
    }


def make_llm(handler, **overrides: Any) -> OpenAICompatibleLLM:
    """Build a client whose network is replaced by the given handler function."""
    return OpenAICompatibleLLM(make_settings(**overrides), transport=httpx2.MockTransport(handler))


def recording_handler(seen: list[httpx2.Request], reply: dict[str, Any] | None = None):
    """Build a handler that records every request it receives and answers with a good reply."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=reply if reply is not None else good_reply())

    return handler


# --- build_request_body ---


def test_request_body_has_the_fields_openai_compatible_servers_expect():
    """The request carries the model name, the messages as role/content pairs, and the limits."""
    body = build_request_body("test-model", MESSAGES, temperature=0.5, max_output_tokens=200)
    assert body == {
        "model": "test-model",
        "messages": [
            {"role": "system", "content": "You are a strict interviewer."},
            {"role": "user", "content": "Grade this answer."},
        ],
        "temperature": 0.5,
        "max_tokens": 200,
    }


def test_request_body_keeps_message_order():
    """Messages are sent in the order given, because the order is the conversation."""
    body = build_request_body("m", list(reversed(MESSAGES)), temperature=0.2, max_output_tokens=10)
    assert [message["role"] for message in body["messages"]] == ["user", "system"]


# --- parse_completion ---


def test_parse_completion_reads_text_model_finish_reason_and_usage():
    """A normal reply becomes a Completion carrying everything the provider reported."""
    completion = parse_completion(good_reply("Fine."), requested_model="asked-for")
    assert completion == Completion(
        text="Fine.",
        model="test-model",
        finish_reason="stop",
        prompt_tokens=12,
        completion_tokens=3,
    )


def test_parse_completion_falls_back_to_the_requested_model_name():
    """If the provider does not name the model, the name we asked for is used."""
    reply = good_reply()
    del reply["model"]
    assert parse_completion(reply, requested_model="asked-for").model == "asked-for"


def test_parse_completion_leaves_usage_empty_when_the_provider_sends_none():
    """Missing usage is not an error: the token counts are simply None."""
    reply = good_reply()
    del reply["usage"]
    completion = parse_completion(reply, requested_model="m")
    assert completion.prompt_tokens is None
    assert completion.completion_tokens is None


@pytest.mark.parametrize("bad_count", [-1, "12", 12.5, True, None])
def test_parse_completion_ignores_token_counts_that_are_not_whole_non_negative_numbers(bad_count):
    """A nonsense token count is dropped instead of crashing the call."""
    reply = good_reply()
    reply["usage"] = {"prompt_tokens": bad_count, "completion_tokens": bad_count}
    completion = parse_completion(reply, requested_model="m")
    assert completion.prompt_tokens is None
    assert completion.completion_tokens is None


def test_parse_completion_keeps_a_length_finish_reason():
    """'length' tells the caller the reply was cut off, so it must reach them."""
    reply = good_reply()
    reply["choices"][0]["finish_reason"] = "length"
    assert parse_completion(reply, requested_model="m").finish_reason == "length"


def test_parse_completion_drops_a_finish_reason_that_is_not_text():
    """A finish reason of the wrong type becomes None."""
    reply = good_reply()
    reply["choices"][0]["finish_reason"] = 7
    assert parse_completion(reply, requested_model="m").finish_reason is None


def test_parse_completion_keeps_nepali_text_unchanged():
    """Devanagari text survives intact, because the product is for Nepali speakers."""
    assert parse_completion(good_reply("नमस्ते"), requested_model="m").text == "नमस्ते"


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"content": "  \n "}}]},
        {"choices": [{"message": {"content": 42}}]},
        {"choices": "abc"},
        {"choices": {"0": 1}},
        [],
        "just text",
        None,
    ],
    ids=repr,
)
def test_parse_completion_rejects_replies_without_usable_text(data):
    """Anything that is not a reply with real text raises LLMResponseError, never another type."""
    with pytest.raises(LLMResponseError):
        parse_completion(data, requested_model="m")


# --- parse_retry_after ---


@pytest.mark.parametrize(
    ("header", "expected"), [("2", 2.0), ("0", 0.0), ("1.5", 1.5), (" 3 ", 3.0)]
)
def test_retry_after_in_seconds_is_understood(header, expected):
    """A Retry-After header holding a number of seconds is read as that number."""
    assert parse_retry_after(header) == expected


@pytest.mark.parametrize(
    "header", [None, "", "soon", "-1", "nan", "inf", "Wed, 21 Oct 2026 07:28:00 GMT"]
)
def test_retry_after_that_is_not_a_usable_number_is_ignored(header):
    """Missing, negative, infinite, or date-style values mean 'no usable wait time'."""
    assert parse_retry_after(header) is None


# --- raise_for_error_status ---


@pytest.mark.parametrize("status", [200, 201, 204])
def test_success_statuses_raise_nothing(status):
    """2xx responses pass through the status check."""
    raise_for_error_status(httpx2.Response(status))


@pytest.mark.parametrize(
    ("status", "error_class"),
    [
        (401, LLMAuthError),
        (403, LLMAuthError),
        (400, LLMRequestError),
        (404, LLMRequestError),
        (422, LLMRequestError),
        (301, LLMRequestError),
        (500, LLMServerError),
        (502, LLMServerError),
        (503, LLMServerError),
    ],
)
def test_each_failure_status_maps_to_its_own_error(status, error_class):
    """The HTTP status decides which gateway error the caller sees."""
    with pytest.raises(error_class) as caught:
        raise_for_error_status(httpx2.Response(status))
    assert caught.type is error_class


def test_rate_limit_error_carries_the_wait_the_provider_asked_for():
    """A 429 with Retry-After gives the caller the number of seconds to wait."""
    response = httpx2.Response(429, headers={"Retry-After": "2.5"})
    with pytest.raises(LLMRateLimitError) as caught:
        raise_for_error_status(response)
    assert caught.value.retry_after == 2.5


def test_rate_limit_error_without_retry_after_has_no_wait():
    """A 429 without Retry-After leaves retry_after as None."""
    with pytest.raises(LLMRateLimitError) as caught:
        raise_for_error_status(httpx2.Response(429))
    assert caught.value.retry_after is None


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(401, False), (400, False), (404, False), (429, True), (500, True), (503, True)],
)
def test_only_temporary_failures_are_marked_retryable(status, retryable):
    """Rate limits and server problems may succeed on a second try; the rest will not."""
    with pytest.raises(LLMError) as caught:
        raise_for_error_status(httpx2.Response(status))
    assert caught.value.retryable is retryable


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"code": "context_length_exceeded", "message": "too big"}},
        {
            "error": {
                "message": "This model's maximum context length is 4096 tokens. "
                "However, your messages resulted in 4239 tokens."
            }
        },
        {"error": {"message": "The prompt does not fit in the context window."}},
        {"error": "Input exceeds the model's context length"},
    ],
    ids=["code", "openai-wording", "window-wording", "plain-string-error"],
)
def test_a_400_about_context_size_becomes_context_budget_exceeded(body):
    """When the provider itself says the prompt is too long, the caller gets the budget error."""
    with pytest.raises(ContextBudgetExceededError) as caught:
        raise_for_error_status(httpx2.Response(400, json=body))
    assert caught.value.estimated_tokens is None
    assert caught.value.budget_tokens is None


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(400, json={"error": {"message": "Unknown parameter: foo"}}),
        httpx2.Response(400, json={"detail": "context length"}),
        httpx2.Response(400, text="<html>bad request</html>"),
        httpx2.Response(500, json={"error": {"message": "context length exceeded"}}),
    ],
    ids=["unrelated-400", "detail-not-error", "not-json", "500-is-not-a-context-error"],
)
def test_other_failures_are_not_mistaken_for_context_errors(response):
    """Only a 400 that really talks about the context size becomes a budget error."""
    with pytest.raises(Exception) as caught:
        raise_for_error_status(response)
    assert not isinstance(caught.value, ContextBudgetExceededError)


def test_a_404_message_points_at_the_two_usual_setup_mistakes():
    """A 404 usually means a wrong address or a wrong model name, and the message says so."""
    with pytest.raises(LLMRequestError) as caught:
        raise_for_error_status(httpx2.Response(404))
    assert "LLM_BASE_URL" in str(caught.value)
    assert "LLM_MODEL" in str(caught.value)


def test_the_status_number_is_in_the_message():
    """The message names the HTTP status so a person can look it up."""
    with pytest.raises(LLMServerError, match="503"):
        raise_for_error_status(httpx2.Response(503))


def test_a_short_provider_error_code_is_shown():
    """The provider's short `code` field is repeated in the message, and nothing else from it."""
    response = httpx2.Response(
        400,
        json={
            "error": {
                "message": "Unsupported parameter: 'temperature' is not supported with this model.",
                "type": "invalid_request_error",
                "param": "temperature",
                "code": "unsupported_parameter",
            }
        },
    )
    with pytest.raises(LLMRequestError) as caught:
        raise_for_error_status(response)
    expected = "The provider rejected the request (HTTP 400, unsupported_parameter)."
    assert str(caught.value) == expected


def test_provider_free_text_never_reaches_the_error_message():
    """Provider error text can echo the prompt, so it is read for decisions but never repeated."""
    secret = "PROMPT-TEXT-ABOUT-MY-RESUME"
    response = httpx2.Response(
        400, json={"error": {"code": f"bad {secret}", "message": f"Bad input: {secret}"}}
    )
    with pytest.raises(LLMRequestError) as caught:
        raise_for_error_status(response)
    assert secret not in str(caught.value)


# --- OpenAICompatibleLLM ---


def test_the_real_client_counts_as_an_llm_and_so_does_any_class_with_complete():
    """LLM is a shape, not a base class: anything with an async complete method fits."""

    class Stub:
        async def complete(self, messages, *, temperature=0.2, max_output_tokens=None):
            return Completion(text="hi", model="stub")

    assert isinstance(make_llm(lambda request: httpx2.Response(200)), LLM)
    assert isinstance(Stub(), LLM)
    assert not isinstance(object(), LLM)


@pytest.mark.anyio
async def test_complete_posts_to_chat_completions_under_the_base_url():
    """The request goes to {base_url}/chat/completions as a POST."""
    seen: list[httpx2.Request] = []
    llm = make_llm(recording_handler(seen), base_url="http://models.test/v1/")
    await llm.complete(MESSAGES)
    assert [(r.method, str(r.url)) for r in seen] == [
        ("POST", "http://models.test/v1/chat/completions")
    ]


@pytest.mark.anyio
async def test_complete_sends_the_configured_model_and_default_limits():
    """With no overrides, the model and the output limit come from the settings."""
    seen: list[httpx2.Request] = []
    llm = make_llm(recording_handler(seen), model="llama3.1:8b", max_output_tokens=300)
    await llm.complete(MESSAGES)
    body = json.loads(seen[0].content)
    assert body["model"] == "llama3.1:8b"
    assert body["max_tokens"] == 300
    assert body["temperature"] == 0.2


@pytest.mark.anyio
async def test_complete_lets_one_call_override_temperature_and_output_limit():
    """A caller can ask for a different temperature or reply length for a single call."""
    seen: list[httpx2.Request] = []
    llm = make_llm(recording_handler(seen))
    await llm.complete(MESSAGES, temperature=0.9, max_output_tokens=50)
    body = json.loads(seen[0].content)
    assert body["temperature"] == 0.9
    assert body["max_tokens"] == 50


@pytest.mark.anyio
async def test_complete_sends_nepali_text_without_damaging_it():
    """Devanagari in a prompt arrives at the server exactly as written."""
    seen: list[httpx2.Request] = []
    llm = make_llm(recording_handler(seen))
    await llm.complete([ChatMessage(role="user", content="नमस्ते, तपाईंलाई कस्तो छ?")])
    body = json.loads(seen[0].content)
    assert body["messages"][0]["content"] == "नमस्ते, तपाईंलाई कस्तो छ?"


@pytest.mark.anyio
async def test_complete_sends_the_api_key_as_a_bearer_token():
    """When a key is configured, every request carries it in the Authorization header."""
    seen: list[httpx2.Request] = []
    llm = make_llm(recording_handler(seen), api_key="sk-test-123")
    await llm.complete(MESSAGES)
    assert seen[0].headers["authorization"] == "Bearer sk-test-123"


@pytest.mark.anyio
async def test_complete_sends_no_authorization_header_without_a_key():
    """Local servers such as Ollama need no key, so none is sent."""
    seen: list[httpx2.Request] = []
    llm = make_llm(recording_handler(seen), api_key=None)
    await llm.complete(MESSAGES)
    assert "authorization" not in seen[0].headers


@pytest.mark.anyio
async def test_complete_returns_the_parsed_completion():
    """The caller gets a Completion built from the provider's reply."""
    llm = make_llm(recording_handler([], good_reply("Well answered.")))
    completion = await llm.complete(MESSAGES)
    assert completion.text == "Well answered."
    assert completion.finish_reason == "stop"
    assert completion.prompt_tokens == 12


@pytest.mark.anyio
async def test_complete_refuses_a_prompt_that_cannot_fit_without_calling_the_server():
    """Our own budget check runs first, so an oversized prompt never costs a request."""
    seen: list[httpx2.Request] = []
    llm = make_llm(recording_handler(seen), context_tokens=512, max_output_tokens=100)
    too_long = [ChatMessage(role="user", content="a" * 3000)]
    with pytest.raises(ContextBudgetExceededError) as caught:
        await llm.complete(too_long)
    assert seen == []
    assert caught.value.budget_tokens == 412


@pytest.mark.anyio
async def test_complete_uses_a_per_call_output_limit_in_the_budget_check():
    """Asking for a longer reply leaves less room for the prompt, and the check knows."""
    llm = make_llm(recording_handler([]), context_tokens=512, max_output_tokens=10)
    prompt = [ChatMessage(role="user", content="a" * 600)]
    await llm.complete(prompt)
    with pytest.raises(ContextBudgetExceededError):
        await llm.complete(prompt, max_output_tokens=400)


@pytest.mark.anyio
async def test_complete_turns_a_timeout_into_llm_timeout_error():
    """If the server takes too long, the caller sees LLMTimeoutError, not an httpx2 error."""

    def handler(request):
        raise httpx2.ReadTimeout("too slow", request=request)

    with pytest.raises(LLMTimeoutError) as caught:
        await make_llm(handler, timeout_seconds=7).complete(MESSAGES)
    assert "7" in str(caught.value)
    assert caught.value.retryable is True


@pytest.mark.anyio
async def test_complete_turns_a_connection_failure_into_llm_connection_error():
    """If the server cannot be reached, the caller sees LLMConnectionError."""

    def handler(request):
        raise httpx2.ConnectError("refused", request=request)

    with pytest.raises(LLMConnectionError) as caught:
        await make_llm(handler).complete(MESSAGES)
    assert "LLM_BASE_URL" in str(caught.value)
    assert caught.value.retryable is True


@pytest.mark.anyio
async def test_complete_turns_an_undecodable_reply_into_llm_response_error():
    """A reply whose body cannot be decoded is a response problem, not a crash."""

    def handler(request):
        raise httpx2.DecodingError("bad gzip", request=request)

    with pytest.raises(LLMResponseError):
        await make_llm(handler).complete(MESSAGES)


@pytest.mark.anyio
async def test_complete_maps_http_failures_through_the_status_check():
    """An HTTP error status from the server becomes the matching gateway error."""
    llm = make_llm(lambda request: httpx2.Response(429, headers={"Retry-After": "4"}))
    with pytest.raises(LLMRateLimitError) as caught:
        await llm.complete(MESSAGES)
    assert caught.value.retry_after == 4.0


@pytest.mark.anyio
async def test_complete_treats_a_non_json_success_reply_as_a_response_error():
    """A 200 with an HTML page usually means LLM_BASE_URL points at a website, not an API."""
    llm = make_llm(lambda request: httpx2.Response(200, text="<html>Welcome</html>"))
    with pytest.raises(LLMResponseError, match="LLM_BASE_URL"):
        await llm.complete(MESSAGES)


@pytest.mark.anyio
async def test_complete_treats_a_reply_without_text_as_a_response_error():
    """A valid JSON reply with no message text still raises LLMResponseError."""
    llm = make_llm(lambda request: httpx2.Response(200, json={"choices": []}))
    with pytest.raises(LLMResponseError):
        await llm.complete(MESSAGES)


@pytest.mark.anyio
async def test_errors_never_contain_the_api_key_or_the_prompt():
    """Error messages are safe to log: no secret key and no prompt text, even on failures."""
    secret_prompt = "MY-PRIVATE-RESUME-TEXT"
    llm = make_llm(
        lambda request: httpx2.Response(401, json={"error": {"message": secret_prompt}}),
        api_key="sk-very-secret",
    )
    with pytest.raises(LLMAuthError) as caught:
        await llm.complete([ChatMessage(role="user", content=secret_prompt)])
    message = str(caught.value)
    assert "sk-very-secret" not in message
    assert secret_prompt not in message


@pytest.mark.anyio
async def test_closing_the_client_stops_it_from_sending_more_requests():
    """After aclose the connection pool is released and further calls fail."""
    llm = make_llm(recording_handler([]))
    await llm.aclose()
    with pytest.raises(RuntimeError):
        await llm.complete(MESSAGES)


@pytest.mark.anyio
async def test_the_client_can_be_used_as_an_async_context_manager():
    """`async with` closes the client automatically when the block ends."""
    async with make_llm(recording_handler([])) as llm:
        assert (await llm.complete(MESSAGES)).text == "Hello there."
    with pytest.raises(RuntimeError):
        await llm.complete(MESSAGES)
