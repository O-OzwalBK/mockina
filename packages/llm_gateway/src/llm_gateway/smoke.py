"""A check you run by hand: ask your real model one question through the whole gateway.

Fill in `.env` (see `.env.example`), then from the repo root:

    uv run python -m llm_gateway.smoke
    uv run python -m llm_gateway.smoke --prompt "Name one sorting algorithm."
    uv run python -m llm_gateway.smoke --direct

It reads the settings, sends the question through the client and the retry wrapper, and
prints the reply and how long it took. If something goes wrong it prints the kind of error
and its message. The result is 0 when the model answered, 1 when the call failed, and 2
when the settings are wrong. It never prints the API key or repeats the question.

This is not a test: it needs a model that is running, so it must never run in CI. It lives
in a module named `smoke`, which pytest does not collect.
"""

import argparse
import asyncio
import sys
import time
from collections.abc import Sequence
from textwrap import indent

from pydantic import ValidationError

from llm_gateway.client import OpenAICompatibleLLM
from llm_gateway.errors import LLMError
from llm_gateway.interface import LLM
from llm_gateway.models import ChatMessage, Completion
from llm_gateway.retry import RetryingLLM
from llm_gateway.settings import LLMSettings

DEFAULT_PROMPT = "Say hello in one short sentence."


def describe_settings(settings: LLMSettings, *, direct: bool) -> str:
    """Say what is about to be asked and of whom, without showing the API key."""

    retries = "no retries (--direct)" if direct else f"up to {settings.max_retries} retries"
    key = "set" if settings.api_key is not None else "not set"
    return (
        f"Asking {settings.model} at {settings.base_url}\n"
        f"  timeout {settings.timeout_seconds:g} s per attempt, {retries}, API key: {key}"
    )


def describe_settings_problem(error: ValidationError) -> str:
    """List what is wrong with the settings by variable name, without repeating the values."""

    lines = ["The settings are not usable, so nothing was sent:"]
    for problem in error.errors():
        location = problem["loc"]
        name = f"LLM_{location[0]}".upper() if location else "settings"
        message = problem["msg"].removeprefix("Value error, ")
        lines.append(f"  {name}: {message}")
    lines.append("Set them in the environment or in .env (see .env.example).")
    return "\n".join(lines)


def describe_details(reply: Completion) -> str:
    """One line with the model name and whatever else the provider reported."""

    parts = [f"model: {reply.model}"]
    if reply.finish_reason is not None:
        parts.append(f"finish reason: {reply.finish_reason}")
    if reply.prompt_tokens is not None:
        parts.append(f"prompt tokens: {reply.prompt_tokens}")
    if reply.completion_tokens is not None:
        parts.append(f"reply tokens: {reply.completion_tokens}")
    return " | ".join(parts)


async def list_models(settings: LLMSettings) -> int:
    try:
        async with OpenAICompatibleLLM(settings) as client:
            models = await client.list_models()
    except LLMError as error:
        print(f"FAILED: {type(error).__name__}")
        print(indent(str(error), "  "))
        return 1

    if not models:
        print("The provider returned no models.")
    else:
        print("Available models:")
        for model in models:
            print(f"  {model}")
    return 0


async def ask(llm: LLM, prompt: str) -> int:
    """Send one question and print what came back. Returns 0 on success and 1 on an LLMError.

    Only LLMError is handled. Any other exception is a bug and keeps its traceback.
    """

    started = time.perf_counter()
    try:
        reply = await llm.complete([ChatMessage(role="user", content=prompt)])
    except LLMError as error:
        elapsed = time.perf_counter() - started
        print(f"FAILED after {elapsed:.1f} s: {type(error).__name__}")
        print(indent(str(error), "  "))
        print(f"  Retryable: {'yes' if error.retryable else 'no'}")
        return 1
    elapsed = time.perf_counter() - started
    print(f"Reply after {elapsed:.1f} s:")
    print(indent(reply.text, "  "))
    print(describe_details(reply))
    return 0


async def run(settings: LLMSettings, prompt: str, *, direct: bool) -> int:
    """Build the client, wrap it in retries unless `direct`, ask, and close the client."""

    async with OpenAICompatibleLLM(settings) as client:
        llm: LLM = client if direct else RetryingLLM(client, max_retries=settings.max_retries)
        return await ask(llm, prompt)


def build_parser() -> argparse.ArgumentParser:
    """Three options:
    - which question to ask
    - whether to skip the retry wrapper
    - list available models from the provider"""

    parser = argparse.ArgumentParser(
        prog="python -m llm_gateway.smoke",
        description="Ask the configured model one question and show what happens.",
    )
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="the question to ask")
    parser.add_argument(
        "--direct",
        action="store_true",
        help="skip the retry wrapper, to see the first failure as it is",
    )
    parser.add_argument(
        "--list-models", action="store_true", help="list model IDs reported by the provider"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Read the settings, show them, ask the question, and return the exit code."""

    arguments = build_parser().parse_args(argv)
    try:
        settings = LLMSettings()  # pyright: ignore[reportCallIssue]
    except ValidationError as error:
        print(describe_settings_problem(error))
        return 2

    if arguments.list_models:
        print(f"Listing models at {settings.base_url}")
        return asyncio.run(list_models(settings))

    print(describe_settings(settings, direct=arguments.direct))
    return asyncio.run(run(settings, arguments.prompt, direct=arguments.direct))


if __name__ == "__main__":
    sys.exit(main())
