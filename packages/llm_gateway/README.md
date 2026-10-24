# llm_gateway

The one door that every call to a language model goes through.

The evaluator (grading an answer) and the interview engine (asking the next question)
each hand this package a conversation and get plain text back. Neither needs to know
which model answered, where it runs, or what a failure looks like on the wire. Pointing
the whole app at another model is a change to two lines in `.env`.

It works with any server that speaks the OpenAI chat API: Ollama, LM Studio, vLLM, or a
hosted provider of open-weight models.

## What it promises

- **One kind of failure.** Every way a call can fail is raised as an `LLMError`. No
  `httpx2` or Pydantic error escapes, so `except LLMError` really does catch them all.
- **Nothing private in errors.** Error messages say what to check. They never contain the
  API key, any part of the prompt, or the provider's own error text.
- **Refuses early.** A prompt that cannot fit the model's context window is rejected
  before a request is spent on it.
- **Retries only what can get better.** Timeouts, connection failures, server errors and
  rate limits are retried with growing pauses. A wrong key or a bad request is not.
- **Testable without a model.** `FakeLLM` stands in for the real thing in tests.

## Quick start

Copy `.env.example` to `.env` in the repo root and fill in the two required lines.

```python
import asyncio

from llm_gateway import ChatMessage, LLMSettings, OpenAICompatibleLLM, RetryingLLM


async def main() -> None:
    settings = LLMSettings()  # reads LLM_* from the environment and .env
    async with OpenAICompatibleLLM(settings) as client:  # one attempt per call
        llm = RetryingLLM(client, max_retries=settings.max_retries)  # retries around it
        reply = await llm.complete(
            [ChatMessage(role="user", content="Say hello in one short sentence.")]
        )
        print(reply.text)


asyncio.run(main())
```

Code that uses a model should accept the `LLM` interface, not a particular class. That is
what lets tests hand it a fake:

```python
from llm_gateway import LLM, ChatMessage


async def grade(llm: LLM, answer: str) -> str:
    reply = await llm.complete([ChatMessage(role="user", content=f"Grade: {answer}")])
    return reply.text
```

## Settings

All settings are environment variables, read once at startup. A bad value stops the app
immediately with a message that names the variable.

| Variable                | Required | Default | Meaning                                                                                                               |
| ----------------------- | -------- | ------- | --------------------------------------------------------------------------------------------------------------------- |
| `LLM_BASE_URL`          | yes      |         | Address of the API, including the `/v1` part. The gateway adds `/chat/completions`.                                   |
| `LLM_MODEL`             | yes      |         | The model's name exactly as the provider lists it.                                                                    |
| `LLM_API_KEY`           | no       | none    | Secret key from the provider. Leave it empty for local servers that need none. Never shown when settings are printed. |
| `LLM_CONTEXT_TOKENS`    | no       | `8192`  | Tokens the model can handle in one request, prompt and reply together. At least 512.                                  |
| `LLM_MAX_OUTPUT_TOKENS` | no       | `1024`  | Longest reply to ask for. Must be smaller than the context size.                                                      |
| `LLM_TIMEOUT_SECONDS`   | no       | `60`    | Seconds to wait for the provider on each attempt.                                                                     |
| `LLM_MAX_RETRIES`       | no       | `2`     | Extra attempts after a temporary failure, from 0 to 5.                                                                |

## Errors

Callers decide what to do with each one. `retryable` says whether trying the same request
again can help, and `RetryingLLM` acts on it.

| Error                        | Meaning                                                                                    | Retried |
| ---------------------------- | ------------------------------------------------------------------------------------------ | ------- |
| `LLMError`                   | Base class of everything below.                                                            |         |
| `LLMConnectionError`         | The server could not be reached: it is down, the address is wrong, or there is no network. | yes     |
| `LLMTimeoutError`            | The server did not answer within `LLM_TIMEOUT_SECONDS`.                                    | yes     |
| `LLMRateLimitError`          | The provider said to slow down (HTTP 429). It may carry `retry_after`, which is obeyed.    | yes     |
| `LLMServerError`             | The provider had a problem on its side (HTTP 500 and above).                               | yes     |
| `LLMAuthError`               | The API key is missing or wrong (HTTP 401 or 403).                                         | no      |
| `LLMRequestError`            | The provider rejected the request itself, for example an unknown model name.               | no      |
| `LLMResponseError`           | The provider answered, but the reply was not in the expected shape or had no text.         | no      |
| `ContextBudgetExceededError` | The prompt is too long for the context window, leaving no room for the reply.              | no      |

## Testing code that uses a model

`FakeLLM` plays back a script instead of calling a model. Each call gets the next outcome:
a string (a successful reply), a `Completion`, or an exception, which is raised.

```python
# `grade` is the function from the example above.
from llm_gateway import LLMServerError, RetryingLLM
from llm_gateway.testing import FakeLLM


async def test_grade_returns_the_model_reply():
    """The reply text is passed back, and the answer reached the model."""
    fake = FakeLLM("Score: 7")
    assert await grade(fake, "A closure keeps its scope alive.") == "Score: 7"
    assert "closure" in fake.calls[0].messages[0].content


async def test_grade_survives_one_temporary_failure():
    """A model that fails once and then answers still gives the answer, after one retry."""
    fake = FakeLLM(LLMServerError("busy"), "Score: 7")
    llm = RetryingLLM(fake, max_retries=1, base_delay_seconds=0)
    assert await grade(llm, "A closure keeps its scope alive.") == "Score: 7"
    assert len(fake.calls) == 2
```

Every call is recorded in `fake.calls` (messages, temperature, reply limit), so a test can
check what was sent. A call beyond the end of the script raises `ScriptExhaustedError`,
which is an `AssertionError` and not an `LLMError`, so a mistake in a test cannot be
swallowed by code that handles model failures. `fake.remaining` tells how many outcomes
were left unused.

`FakeLLM` is imported from `llm_gateway.testing`, not from the top level, because
production code has no use for it.

## What it does not do

- **No streaming.** A call returns when the whole reply is ready.
- **No JSON mode and no tool calls.** The caller parses the text and decides what to do
  with a reply that is not what it asked for.
- **No exact token counting.** The context check uses a cautious estimate that rounds up
  and counts non-ASCII text, including Devanagari, as whole tokens. The provider's own
  counts come back on the `Completion`.
- **No overall time limit yet.** Each attempt can use the full timeout, so the worst case
  for one call is `(LLM_MAX_RETRIES + 1)` timeouts plus the pauses, about three minutes
  with the defaults. Lower `LLM_TIMEOUT_SECONDS` or `LLM_MAX_RETRIES` for interactive use.

## Reading JSON from a model reply

`parse_json_reply(text)` is a shared reader for packages whose prompts request JSON. It tries the
entire reply first; otherwise it scans the reply for complete top-level objects and arrays and
returns the **last** one that parses. A model usually reasons or shows a shape example before it
writes the real answer, so the final value is the useful one. Nested objects inside the answer are
not treated as separate answers. The scanner understands quoted strings and escapes, and returns
any JSON value; the calling package is responsible for validating its expected shape.

If no candidate parses, it raises `ReplyNotJsonError`, a `ValueError` that is deliberately not an
`LLMError`. The message never includes model text. Transport retries therefore do not repeat an
identical parse failure; a package may choose a bounded repair request when its domain warrants it.
The helper accepts reply text, not a `Completion`, so each caller decides how to handle
`finish_reason="length"` before parsing.

## Development

From the repo root:

```
uv sync --all-packages
uv run pytest packages/llm_gateway
```
