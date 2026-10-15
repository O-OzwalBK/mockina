import asyncio
import socket

import pytest
from llm_gateway import (
    ChatMessage,
    LLMConnectionError,
    LLMSettings,
    LLMTimeoutError,
    OpenAICompatibleLLM,
)

MESSAGES = [ChatMessage(role="user", content="Hello.")]


@pytest.fixture
def anyio_backend():
    """Run the async tests on asyncio only."""
    return "asyncio"


@pytest.fixture(autouse=True)
def no_proxy_for_local_tests(monkeypatch):
    """Make sure a proxy set on the machine cannot get between these tests and localhost."""
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.delenv(name, raising=False)


def settings_for(port: int, timeout_seconds: float = 2.0) -> LLMSettings:
    """Settings that point at a server on this computer, whatever the real environment says.

    Every field is given, because a field left out would still be read from an exported LLM_ variable. `_env_file=None` only switches off the .env file.

    The default timeout is short, and that is safe. Linux and macOS refuse a connection to a closed port at once, but Windows keeps resending the connection request for a few seconds before it reports the refusal, so a short timeout can end the wait first. The client reports both outcomes as LLMConnectionError, so the test does not depend on the system.
    """
    # pydantic-settings accepts `_env_file`, but Pylance cannot see it.
    return LLMSettings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        base_url=f"http://127.0.0.1:{port}/v1",
        model="test-model",
        api_key=None,
        context_tokens=8192,
        max_output_tokens=1024,
        timeout_seconds=timeout_seconds,
        max_retries=0,
    )


@pytest.mark.anyio
async def test_nothing_listening_raises_llm_connection_error():
    """With no server at the address, the real network stack's refusal becomes LLMConnectionError."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        unused_port = probe.getsockname()[1]
    async with OpenAICompatibleLLM(settings_for(unused_port)) as llm:
        with pytest.raises(LLMConnectionError):
            await llm.complete(MESSAGES)


@pytest.mark.anyio
async def test_a_server_that_never_answers_raises_llm_timeout_error():
    """A server that accepts the request but stays silent hits the time limit as LLMTimeoutError."""
    release = asyncio.Event()

    async def never_answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.read(65536)
        await release.wait()
        writer.close()

    server = await asyncio.start_server(never_answer, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        async with OpenAICompatibleLLM(settings_for(port, timeout_seconds=0.3)) as llm:
            with pytest.raises(LLMTimeoutError):
                await llm.complete(MESSAGES)
    finally:
        release.set()
        server.close()
        await server.wait_closed()
