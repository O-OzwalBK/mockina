import re
from collections.abc import Sequence
from math import isfinite
from typing import Any, Self

import httpx2

from llm_gateway.budget import check_context_budget
from llm_gateway.errors import (
    ContextBudgetExceededError,
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMServerError,
    LLMTimeoutError,
)
from llm_gateway.models import ChatMessage, Completion
from llm_gateway.settings import LLMSettings

# Providers phrase "your prompt is too long" differently, so a 400 is treated as a context
# error when its code or its text contains one of these.
CONTEXT_ERROR_CODE = "context_length_exceeded"
CONTEXT_ERROR_PHRASES = ("context length", "context_length", "context window")

# A provider error code is only repeated in our messages if it looks like an identifier.
SAFE_ERROR_CODE = re.compile(r"[A-Za-z0-9_.-]{1,64}")


def build_request_body(
    model: str,
    messages: Sequence[ChatMessage],
    *,
    temperature: float,
    max_output_tokens: int,
) -> dict[str, Any]:
    """Build the JSON body that OpenAI-compatible servers expect for a chat request."""
    return {
        "model": model,
        "messages": [{"role": message.role, "content": message.content} for message in messages],
        "temperature": temperature,
        "max_tokens": max_output_tokens,
    }


def read_token_count(value: object) -> int | None:
    """Return a provider-reported token count, or None if it is not a whole number of 0 or more."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def parse_completion(data: Any, *, requested_model: str) -> Completion:
    """Turn the provider's decoded JSON reply into a Completion.

    Raises LLMResponseError if the reply has no usable text, so a malformed reply can
    never leak out as some other kind of exception.
    """
    try:
        choice = data["choices"][0]
        text = choice["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LLMResponseError(
            "The reply had no choices[0].message.content. Check that LLM_BASE_URL points at "
            "an OpenAI-compatible chat API."
        ) from None
    if not isinstance(text, str) or not text.strip():
        raise LLMResponseError("The model returned no text.")

    model = data.get("model")
    if not isinstance(model, str) or not model.strip():
        model = requested_model
    finish_reason = choice.get("finish_reason")
    usage = data.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    return Completion(
        text=text,
        model=model,
        finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        prompt_tokens=read_token_count(usage.get("prompt_tokens")),
        completion_tokens=read_token_count(usage.get("completion_tokens")),
    )


def parse_retry_after(header: str | None) -> float | None:
    """Read a Retry-After header given as a number of seconds; anything else gives None."""
    if header is None:
        return None
    try:
        seconds = float(header)
    except ValueError:
        return None
    if not isfinite(seconds) or seconds < 0:
        return None
    return seconds


def read_error_details(response: httpx2.Response) -> tuple[str | None, str]:
    """Pull the provider's error code and error text out of an error reply, if it has them.

    Servers disagree on the shape: `{"error": {"code": ..., "message": ...}}` is the usual
    one and `{"error": "text"}` also occurs. The result is only used to decide what kind
    of error happened and is never copied into an error message, because the text can echo
    parts of the prompt.
    """
    try:
        body = response.json()
    except ValueError:
        return None, ""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, str):
        return None, error
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message")
        return (
            code if isinstance(code, str) else None,
            message if isinstance(message, str) else "",
        )
    return None, ""


def mentions_context_limit(code: str | None, message: str) -> bool:
    """Say whether a provider error code or text is complaining that the prompt is too long."""
    if code == CONTEXT_ERROR_CODE:
        return True
    lowered = message.lower()
    return any(phrase in lowered for phrase in CONTEXT_ERROR_PHRASES)


def raise_for_error_status(response: httpx2.Response) -> None:
    """Do nothing for a successful reply; raise the matching LLMError for any other status."""
    status = response.status_code
    if 200 <= status < 300:
        return
    code, message = read_error_details(response)
    if status in (401, 403):
        raise LLMAuthError(f"The provider rejected the API key (HTTP {status}). Check LLM_API_KEY.")
    if status == 429:
        raise LLMRateLimitError(
            "The provider says requests are arriving too fast (HTTP 429).",
            retry_after=parse_retry_after(response.headers.get("retry-after")),
        )
    if status >= 500:
        raise LLMServerError(f"The provider had a problem on its side (HTTP {status}).")
    if status == 400 and mentions_context_limit(code, message):
        raise ContextBudgetExceededError(
            "The provider says the prompt is too long for the model's context window."
        )
    if status == 404:
        raise LLMRequestError(
            "The provider could not find that address or model (HTTP 404). Check that "
            "LLM_BASE_URL ends in /v1 and that LLM_MODEL names a model the server has."
        )
    if 300 <= status < 400:
        raise LLMRequestError(
            f"The provider redirected the request (HTTP {status}). Check LLM_BASE_URL, for "
            "example http versus https."
        )
    suffix = f", {code}" if code and SAFE_ERROR_CODE.fullmatch(code) else ""
    raise LLMRequestError(f"The provider rejected the request (HTTP {status}{suffix}).")


class OpenAICompatibleLLM:
    """Talks to any server that speaks the OpenAI chat completions protocol.

    That covers Ollama, LM Studio, vLLM, llama.cpp's server, and hosted providers of
    open-weight models. Which one it talks to is decided only by LLMSettings. A
    `transport` can be passed in tests to replace the network. Close the client with
    `aclose()`, or use it in an `async with` block, when you are done with it.
    """

    def __init__(
        self, settings: LLMSettings, *, transport: httpx2.AsyncBaseTransport | None = None
    ) -> None:
        self._settings = settings
        headers: dict[str, str] = {}
        if settings.api_key is not None:
            headers["Authorization"] = f"Bearer {settings.api_key.get_secret_value()}"
        self._client = httpx2.AsyncClient(
            base_url=settings.base_url,
            headers=headers,
            timeout=settings.timeout_seconds,
            transport=transport,
        )

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ) -> Completion:
        """Send the conversation to the model and return its reply.

        Makes one attempt: it does not retry. Raises ContextBudgetExceededError before
        sending anything if the prompt cannot fit, and another LLMError for every kind of
        failure while talking to the server.
        """
        if max_output_tokens is None:
            max_output_tokens = self._settings.max_output_tokens
        check_context_budget(
            messages,
            context_tokens=self._settings.context_tokens,
            max_output_tokens=max_output_tokens,
        )
        body = build_request_body(
            self._settings.model,
            messages,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        try:
            response = await self._client.post("/chat/completions", json=body)
        except httpx2.ConnectTimeout as error:
            raise LLMConnectionError(
                f"Could not connect to the model server within "
                f"{self._settings.timeout_seconds:g} seconds. Check that it is running and that LLM_BASE_URL is correct."
            ) from error
        except httpx2.TimeoutException as error:
            raise LLMTimeoutError(
                f"The model server did not answer within {self._settings.timeout_seconds:g} seconds. A model that is still loading may need a larger LLM_TIMEOUT_SECONDS."
            ) from error
        except httpx2.TransportError as error:
            raise LLMConnectionError(
                "Could not reach the model server. Check that it is running and that LLM_BASE_URL is correct."
            ) from error
        except httpx2.DecodingError as error:
            raise LLMResponseError("The model server's reply could not be decoded.") from error

        raise_for_error_status(response)
        try:
            data = response.json()
        except ValueError as error:
            raise LLMResponseError(
                "The reply was not valid JSON. Check that LLM_BASE_URL points at an OpenAI-compatible API, usually ending in /v1."
            ) from error
        return parse_completion(data, requested_model=self._settings.model)

    async def aclose(self) -> None:
        """Release the network connections held by this client."""
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
