"""Tests for MeteredLLM: it adds up the usage of one job's model calls and keeps no content."""

import pytest
from api.model_calls import MeteredLLM
from llm_gateway import ChatMessage, Completion, LLMTimeoutError
from llm_gateway.testing import FakeLLM


@pytest.fixture
def anyio_backend():
    """Run these asynchronous tests on asyncio only."""
    return "asyncio"


def reply(prompt_tokens: int | None, completion_tokens: int | None) -> Completion:
    """A model reply that reports the given token counts."""
    return Completion(
        text="ok",
        model="fake-model",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


MESSAGES = [ChatMessage(role="user", content="hello")]


@pytest.mark.anyio
async def test_it_returns_the_reply_unchanged_and_passes_the_options_on():
    """The wrapped model sees the same messages and options, and its reply comes back as is."""
    fake = FakeLLM(reply(3, 4))
    metered = MeteredLLM(fake)

    completion = await metered.complete(MESSAGES, temperature=0.5, max_output_tokens=50)

    assert completion.text == "ok"
    assert fake.calls[0].temperature == 0.5
    assert fake.calls[0].max_output_tokens == 50
    assert fake.calls[0].messages == tuple(MESSAGES)


@pytest.mark.anyio
async def test_it_adds_up_calls_and_tokens_across_several_calls():
    """A job that calls the model twice reports two calls and the summed token counts."""
    metered = MeteredLLM(FakeLLM(reply(10, 2), reply(5, 1)))

    await metered.complete(MESSAGES)
    await metered.complete(MESSAGES)

    assert metered.calls == 2
    assert metered.prompt_tokens == 15
    assert metered.completion_tokens == 3


@pytest.mark.anyio
async def test_unreported_token_counts_stay_unknown_instead_of_becoming_zero():
    """A provider that reports no usage gives None, not a misleading 0."""
    metered = MeteredLLM(FakeLLM(reply(None, None)))

    await metered.complete(MESSAGES)

    assert metered.calls == 1
    assert metered.prompt_tokens is None
    assert metered.completion_tokens is None


@pytest.mark.anyio
async def test_a_call_that_fails_is_counted_and_the_error_passes_through():
    """The error reaches the caller unchanged, and the failed attempt still counts as a call."""
    metered = MeteredLLM(FakeLLM(LLMTimeoutError("too slow")))

    with pytest.raises(LLMTimeoutError):
        await metered.complete(MESSAGES)

    assert metered.calls == 1
    assert metered.prompt_tokens is None


@pytest.mark.anyio
async def test_it_remembers_only_counts_never_the_messages_or_the_reply():
    """Only numbers are kept, so logging the totals can never leak a prompt or an answer."""
    metered = MeteredLLM(FakeLLM(reply(3, 4)))

    await metered.complete([ChatMessage(role="user", content="secret-prompt-text")])

    kept = {name: value for name, value in vars(metered).items() if name != "_llm"}
    assert kept == {"calls": 1, "prompt_tokens": 3, "completion_tokens": 4}
