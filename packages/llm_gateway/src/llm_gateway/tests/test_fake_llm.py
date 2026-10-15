import asyncio

import pytest
from llm_gateway import (
    LLM,
    ChatMessage,
    Completion,
    LLMError,
    LLMServerError,
    LLMTimeoutError,
)
from llm_gateway.testing import FAKE_MODEL_NAME, FakeLLM, RecordedCall, ScriptExhaustedError
from pydantic import ValidationError

MESSAGES = [ChatMessage(role="user", content="Grade this answer.")]


@pytest.fixture
def anyio_backend():
    """Run the async tests on asyncio only."""
    return "asyncio"


# what a script can hold


@pytest.mark.anyio
async def test_a_string_is_played_back_as_a_completion():
    """A plain string in the script is shorthand for a successful reply with that text."""
    completion = await FakeLLM("Score: 7").complete(MESSAGES)
    assert completion == Completion(text="Score: 7", model=FAKE_MODEL_NAME)


@pytest.mark.anyio
async def test_a_completion_is_returned_exactly_as_given():
    """A Completion in the script comes back untouched, so tests can set token counts or a finish reason."""
    reply = Completion(text="cut off", model="m", finish_reason="length", prompt_tokens=10)
    assert await FakeLLM(reply).complete(MESSAGES) is reply


@pytest.mark.anyio
async def test_an_exception_in_the_script_is_raised_as_the_same_object():
    """An error in the script is raised, not returned, so tests can simulate any failure."""
    error = LLMServerError("busy")
    with pytest.raises(LLMServerError) as caught:
        await FakeLLM(error).complete(MESSAGES)
    assert caught.value is error


@pytest.mark.anyio
async def test_any_exception_can_be_scripted_even_a_cancellation():
    """Even a BaseException such as CancelledError can be scripted, to test that code lets it through."""
    with pytest.raises(asyncio.CancelledError):
        await FakeLLM(asyncio.CancelledError()).complete(MESSAGES)


def test_an_empty_string_is_refused_when_the_script_is_built():
    """A reply cannot be empty, and the mistake shows at the line that built the script, not inside the code under test."""
    with pytest.raises(ValidationError):
        FakeLLM("")


# how it plays the script


@pytest.mark.anyio
async def test_outcomes_are_played_back_in_order_one_per_call():
    """The first call gets the first outcome, the second call the second, and so on."""
    fake = FakeLLM("first", LLMTimeoutError("slow"), "third")
    assert (await fake.complete(MESSAGES)).text == "first"
    with pytest.raises(LLMTimeoutError):
        await fake.complete(MESSAGES)
    assert (await fake.complete(MESSAGES)).text == "third"


@pytest.mark.anyio
async def test_asking_for_more_replies_than_were_scripted_raises_a_clear_error():
    """A call beyond the end of the script is refused, and the message says which call and how many were scripted."""
    fake = FakeLLM("only one")
    await fake.complete(MESSAGES)
    with pytest.raises(ScriptExhaustedError, match=r"reply number 2, but the script holds 1"):
        await fake.complete(MESSAGES)


@pytest.mark.anyio
async def test_an_empty_script_refuses_the_very_first_call():
    """A FakeLLM with nothing scripted refuses every call instead of inventing an answer."""
    with pytest.raises(ScriptExhaustedError, match=r"reply number 1, but the script holds 0"):
        await FakeLLM().complete(MESSAGES)


def test_running_out_of_script_is_not_an_llm_error():
    """Code that catches LLMError must not swallow a mistake in the test, so this error is an AssertionError instead."""
    assert not issubclass(ScriptExhaustedError, LLMError)
    assert issubclass(ScriptExhaustedError, AssertionError)


@pytest.mark.anyio
async def test_remaining_counts_the_outcomes_not_used_yet():
    """`remaining` falls by one per call and never goes below zero, so a test can assert the script was fully used."""
    fake = FakeLLM("a", "b")
    assert fake.remaining == 2
    await fake.complete(MESSAGES)
    assert fake.remaining == 1
    await fake.complete(MESSAGES)
    assert fake.remaining == 0
    with pytest.raises(ScriptExhaustedError):
        await fake.complete(MESSAGES)
    assert fake.remaining == 0


# what it remembers


@pytest.mark.anyio
async def test_every_call_is_recorded_with_what_it_was_given():
    """The messages, temperature and reply limit of each call are kept, so a test can check what was sent."""
    fake = FakeLLM("ok")
    await fake.complete(MESSAGES, temperature=0.7, max_output_tokens=200)
    assert fake.calls == [
        RecordedCall(messages=tuple(MESSAGES), temperature=0.7, max_output_tokens=200)
    ]


@pytest.mark.anyio
async def test_defaults_are_recorded_the_way_the_real_client_would_see_them():
    """Not giving a temperature or limit records the protocol defaults: 0.2 and None."""
    fake = FakeLLM("ok")
    await fake.complete(MESSAGES)
    assert fake.calls[0].temperature == 0.2
    assert fake.calls[0].max_output_tokens is None


@pytest.mark.anyio
async def test_a_call_that_fails_is_recorded_too():
    """Calls that raise still count, so a test can check how many attempts were made."""
    fake = FakeLLM(LLMServerError("busy"), "ok")
    with pytest.raises(LLMServerError):
        await fake.complete(MESSAGES)
    await fake.complete(MESSAGES)
    assert len(fake.calls) == 2


@pytest.mark.anyio
async def test_a_refused_call_is_recorded_too():
    """Even the call that ran past the end of the script is in the record, which shows what the code under test asked."""
    fake = FakeLLM("ok")
    await fake.complete(MESSAGES)
    with pytest.raises(ScriptExhaustedError):
        await fake.complete(MESSAGES)
    assert len(fake.calls) == 2


@pytest.mark.anyio
async def test_the_recorded_messages_do_not_change_when_the_caller_changes_its_list():
    """The record is a snapshot: adding to the caller's list afterwards does not rewrite what was sent."""
    fake = FakeLLM("ok")
    conversation = [ChatMessage(role="user", content="First.")]
    await fake.complete(conversation)
    conversation.append(ChatMessage(role="user", content="Added later."))
    assert [message.content for message in fake.calls[0].messages] == ["First."]


# fitting in


def test_a_fake_counts_as_an_llm():
    """Anything that accepts an LLM accepts a FakeLLM, which is the point of having the interface."""
    assert isinstance(FakeLLM(), LLM)


@pytest.mark.anyio
async def test_each_fake_has_its_own_script_and_record():
    """Two fakes never share calls or outcomes."""
    first, second = FakeLLM("a"), FakeLLM("b")
    await first.complete(MESSAGES)
    assert len(first.calls) == 1
    assert second.calls == []
    assert second.remaining == 1
