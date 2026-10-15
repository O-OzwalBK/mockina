import asyncio
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
    RetryingLLM,
)
from llm_gateway.testing import FakeLLM

MESSAGES = [ChatMessage(role="user", content="Grade this answer.")]
REPLY = Completion(text="ok", model="test-model")


@pytest.fixture
def anyio_backend():
    """Use anysyncio backend for async tests"""
    return "asyncio"


class Sleeps:
    """A stand-in for asyncio.sleep that writes the waits down instead of waiting."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def make_retrying(
    inner: LLM, *, max_retries: int = 3, jitter: float = 1.0, **overrides: Any
) -> tuple[RetryingLLM, Sleeps]:
    """Build a RetryingLLM that never really waits and whose 'randomness' is a fixed number."""
    sleeps = Sleeps()
    retrying = RetryingLLM(
        inner,
        max_retries=max_retries,
        sleep=sleeps,
        jitter=lambda: jitter,
        **overrides,
    )
    return retrying, sleeps


# what is retried and what is not


@pytest.mark.anyio
async def test_a_reply_on_the_first_try_is_returned_without_waiting():
    """When nothing goes wrong there is exactly one call and no pause."""
    inner = FakeLLM(REPLY)
    retrying, sleeps = make_retrying(inner)
    assert await retrying.complete(MESSAGES) == REPLY
    assert len(inner.calls) == 1
    assert sleeps.delays == []


@pytest.mark.anyio
async def test_a_temporary_error_is_retried_and_the_later_reply_is_returned():
    """A failure that may pass is followed by a pause and another attempt."""
    inner = FakeLLM(LLMServerError("busy"), REPLY)
    retrying, sleeps = make_retrying(inner)
    assert await retrying.complete(MESSAGES) == REPLY
    assert len(inner.calls) == 2
    assert sleeps.delays == [0.5]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error_class", [LLMTimeoutError, LLMConnectionError, LLMServerError, LLMRateLimitError]
)
async def test_every_temporary_kind_of_error_is_retried(error_class):
    """Timeouts, refused connections, server errors and rate limits are all worth a second try."""
    inner = FakeLLM(error_class("temporary"), REPLY)
    retrying, _ = make_retrying(inner)
    assert await retrying.complete(MESSAGES) == REPLY
    assert len(inner.calls) == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error_class",
    [LLMAuthError, LLMRequestError, LLMResponseError, ContextBudgetExceededError],
)
async def test_errors_that_will_not_get_better_are_raised_at_once(error_class):
    """A wrong key, a bad request or a too-long prompt fails the same way every time."""
    inner = FakeLLM(error_class("permanent"), REPLY)
    retrying, sleeps = make_retrying(inner)
    with pytest.raises(error_class, match="permanent"):
        await retrying.complete(MESSAGES)
    assert len(inner.calls) == 1
    assert sleeps.delays == []


@pytest.mark.anyio
async def test_errors_that_are_not_llm_errors_are_not_retried():
    """A bug is not a temporary failure: it passes through untouched and is not repeated."""
    inner = FakeLLM(ValueError("a bug"), REPLY)
    retrying, sleeps = make_retrying(inner)
    with pytest.raises(ValueError, match="a bug"):
        await retrying.complete(MESSAGES)
    assert len(inner.calls) == 1
    assert sleeps.delays == []


# how many times


@pytest.mark.anyio
async def test_it_gives_up_after_max_retries_and_raises_the_last_error():
    """max_retries=2 means three attempts in all, and the caller sees the final failure."""
    inner = FakeLLM(
        LLMServerError("first"), LLMServerError("second"), LLMServerError("third"), REPLY
    )
    retrying, sleeps = make_retrying(inner, max_retries=2)
    with pytest.raises(LLMServerError, match="third"):
        await retrying.complete(MESSAGES)
    assert len(inner.calls) == 3
    assert sleeps.delays == [0.5, 1.0]


@pytest.mark.anyio
async def test_max_retries_zero_means_a_single_attempt():
    """Zero retries switches the feature off: one call, and the error goes straight out."""
    inner = FakeLLM(LLMTimeoutError("slow"), REPLY)
    retrying, sleeps = make_retrying(inner, max_retries=0)
    with pytest.raises(LLMTimeoutError):
        await retrying.complete(MESSAGES)
    assert len(inner.calls) == 1
    assert sleeps.delays == []


# how long each pause is


@pytest.mark.anyio
async def test_waits_double_each_time_and_stop_growing_at_the_cap():
    """With full delays the pauses go 0.5, 1, 2, 4 and then stay at the 8 second cap."""
    inner = FakeLLM(*[LLMServerError("busy")] * 7)
    retrying, sleeps = make_retrying(inner, max_retries=6)
    with pytest.raises(LLMServerError):
        await retrying.complete(MESSAGES)
    assert sleeps.delays == [0.5, 1.0, 2.0, 4.0, 8.0, 8.0]


@pytest.mark.anyio
async def test_a_huge_retry_count_does_not_overflow_the_delay_arithmetic():
    """Two to the power of 1,100 does not fit in a float, so the doubling must be stopped early."""
    inner = FakeLLM(*[LLMServerError("busy")] * 1101)
    retrying, sleeps = make_retrying(inner, max_retries=1100)
    with pytest.raises(LLMServerError):
        await retrying.complete(MESSAGES)
    assert len(sleeps.delays) == 1100
    assert max(sleeps.delays) == 8.0


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("jitter", "expected"),
    [(1.0, [0.5, 1.0, 2.0]), (0.5, [0.25, 0.5, 1.0]), (0.0, [0.0, 0.0, 0.0])],
)
async def test_jitter_scales_each_pause_between_nothing_and_the_full_delay(jitter, expected):
    """The random factor shrinks every pause, so many clients do not retry at the same moment."""
    inner = FakeLLM(*[LLMServerError("busy")] * 4)
    retrying, sleeps = make_retrying(inner, max_retries=3, jitter=jitter)
    with pytest.raises(LLMServerError):
        await retrying.complete(MESSAGES)
    assert sleeps.delays == expected


@pytest.mark.anyio
async def test_the_base_and_cap_of_the_delay_can_be_chosen():
    """base_delay_seconds and max_delay_seconds set where the doubling starts and stops."""
    inner = FakeLLM(*[LLMServerError("busy")] * 4)
    retrying, sleeps = make_retrying(
        inner, max_retries=3, base_delay_seconds=1.0, max_delay_seconds=3.0
    )
    with pytest.raises(LLMServerError):
        await retrying.complete(MESSAGES)
    assert sleeps.delays == [1.0, 2.0, 3.0]


# what the provider asks for


@pytest.mark.anyio
async def test_a_retry_after_from_the_provider_replaces_the_backoff():
    """When the provider says how long to wait, we wait that long, not our own guess."""
    inner = FakeLLM(LLMRateLimitError("slow down", retry_after=3.0), REPLY)
    retrying, sleeps = make_retrying(inner)
    assert await retrying.complete(MESSAGES) == REPLY
    assert sleeps.delays == [3.0]


@pytest.mark.anyio
async def test_a_retry_after_of_zero_is_obeyed_and_not_mistaken_for_missing():
    """Zero is a real answer ('retry now'), so it must not fall back to the backoff."""
    inner = FakeLLM(LLMRateLimitError("go ahead", retry_after=0.0), REPLY)
    retrying, sleeps = make_retrying(inner)
    assert await retrying.complete(MESSAGES) == REPLY
    assert sleeps.delays == [0.0]


@pytest.mark.anyio
async def test_a_rate_limit_without_retry_after_uses_the_backoff():
    """No hint from the provider means the normal doubling delays apply."""
    inner = FakeLLM(LLMRateLimitError("slow down"), REPLY)
    retrying, sleeps = make_retrying(inner)
    assert await retrying.complete(MESSAGES) == REPLY
    assert sleeps.delays == [0.5]


@pytest.mark.anyio
async def test_a_retry_after_exactly_at_the_cap_is_waited_for():
    """The cap is the longest wait we accept, so a request for exactly that is fine."""
    inner = FakeLLM(LLMRateLimitError("slow down", retry_after=8.0), REPLY)
    retrying, sleeps = make_retrying(inner)
    assert await retrying.complete(MESSAGES) == REPLY
    assert sleeps.delays == [8.0]


@pytest.mark.anyio
async def test_a_retry_after_longer_than_the_cap_is_not_waited_for():
    """A person is waiting on this call, so a one minute wait is refused and the error raised."""
    inner = FakeLLM(LLMRateLimitError("slow down", retry_after=60.0), REPLY)
    retrying, sleeps = make_retrying(inner)
    with pytest.raises(LLMRateLimitError) as caught:
        await retrying.complete(MESSAGES)
    assert caught.value.retry_after == 60.0
    assert len(inner.calls) == 1
    assert sleeps.delays == []


# what is passed along


@pytest.mark.anyio
async def test_every_attempt_gets_the_same_conversation_and_settings():
    """A retry repeats the request exactly: same messages, temperature and reply limit."""

    inner = FakeLLM(LLMTimeoutError("slow"), REPLY)
    retrying, _ = make_retrying(inner)
    await retrying.complete(MESSAGES, temperature=0.7, max_output_tokens=200)
    first, second = inner.calls
    assert first == second
    assert first.messages == tuple(MESSAGES)
    assert first.temperature == 0.7
    assert first.max_output_tokens == 200


@pytest.mark.anyio
async def test_the_default_settings_are_passed_on_as_they_are():
    """Not giving a temperature or limit means the wrapped LLM uses its own defaults."""

    inner = FakeLLM(REPLY)
    retrying, _ = make_retrying(inner)
    await retrying.complete(MESSAGES)
    assert inner.calls[0].temperature == 0.2
    assert inner.calls[0].max_output_tokens is None


@pytest.mark.anyio
async def test_cancelling_during_a_pause_stops_the_retrying():
    """If the caller is cancelled while we wait, the cancellation goes out and nothing else runs."""

    async def cancelled_sleep(seconds: float) -> None:
        raise asyncio.CancelledError

    inner = FakeLLM(LLMServerError("busy"), REPLY)
    retrying = RetryingLLM(inner, max_retries=3, sleep=cancelled_sleep)
    with pytest.raises(asyncio.CancelledError):
        await retrying.complete(MESSAGES)
    assert len(inner.calls) == 1


# construction


def test_the_wrapper_counts_as_an_llm_itself():
    """Anything that accepts an LLM accepts a RetryingLLM, so wrappers can be stacked."""
    assert isinstance(RetryingLLM(FakeLLM(), max_retries=1), LLM)


@pytest.mark.parametrize(
    "bad_arguments",
    [
        {"max_retries": -1},
        {"max_retries": 1, "base_delay_seconds": -0.1},
        {"max_retries": 1, "base_delay_seconds": 2.0, "max_delay_seconds": 1.0},
    ],
    ids=["negative-retries", "negative-base", "cap-below-base"],
)
def test_values_that_make_no_sense_are_refused_when_building(bad_arguments):
    """A wrong number is reported when the wrapper is built, not in the middle of an interview."""
    with pytest.raises(ValueError):
        RetryingLLM(FakeLLM(), **bad_arguments)


@pytest.mark.anyio
async def test_the_real_sleep_and_randomness_are_used_when_none_are_given():
    """Left to its defaults the wrapper really pauses (here for a millisecond) and still works."""
    inner = FakeLLM(LLMServerError("busy"), REPLY)
    retrying = RetryingLLM(inner, max_retries=1, base_delay_seconds=0.001, max_delay_seconds=0.001)
    assert await retrying.complete(MESSAGES) == REPLY
    assert len(inner.calls) == 2


# together with the real client


def make_settings() -> LLMSettings:
    """Settings for the real client, with every field given so the environment cannot change them."""
    return LLMSettings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        base_url="http://models.test/v1",
        model="test-model",
        api_key=None,
        context_tokens=8192,
        max_output_tokens=1024,
        timeout_seconds=30.0,
        max_retries=0,
    )


def good_response() -> httpx2.Response:
    """A successful reply in the shape OpenAI-compatible servers send."""
    return httpx2.Response(
        200,
        json={
            "model": "test-model",
            "choices": [
                {"message": {"role": "assistant", "content": "Hello."}, "finish_reason": "stop"}
            ],
        },
    )


def pretend_server(*responses: httpx2.Response) -> tuple[OpenAICompatibleLLM, list[httpx2.Request]]:
    """A real client wired to a fake server that answers with the given responses in order."""
    queue = list(responses)
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return queue.pop(0)

    return OpenAICompatibleLLM(make_settings(), transport=httpx2.MockTransport(handler)), seen


@pytest.mark.anyio
async def test_two_server_errors_then_a_good_reply_come_out_as_one_reply():
    """With the real client underneath, 503, 503, 200 is three requests and one Completion."""
    client, seen = pretend_server(httpx2.Response(503), httpx2.Response(503), good_response())
    retrying, sleeps = make_retrying(client)
    completion = await retrying.complete(MESSAGES)
    assert completion.text == "Hello."
    assert len(seen) == 3
    assert sleeps.delays == [0.5, 1.0]


@pytest.mark.anyio
async def test_a_rejected_key_is_sent_once_and_not_retried():
    """With the real client underneath, a 401 is one request and an LLMAuthError."""
    client, seen = pretend_server(httpx2.Response(401), good_response())
    retrying, sleeps = make_retrying(client)
    with pytest.raises(LLMAuthError):
        await retrying.complete(MESSAGES)
    assert len(seen) == 1
    assert sleeps.delays == []


@pytest.mark.anyio
async def test_a_429_with_a_retry_after_header_is_waited_for_end_to_end():
    """The header is read by the client and obeyed by the wrapper: Retry-After: 2 means 2 seconds."""
    client, seen = pretend_server(
        httpx2.Response(429, headers={"Retry-After": "2"}), good_response()
    )
    retrying, sleeps = make_retrying(client)
    assert (await retrying.complete(MESSAGES)).text == "Hello."
    assert len(seen) == 2
    assert sleeps.delays == [2.0]
