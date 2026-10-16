from typing import Any

from llm_gateway import ChatMessage
from pydantic import BaseModel, Field, model_validator

MAX_MESSAGES = 100
MAX_MESSAGE_CHARS = 20_000
MAX_TOTAL_MESSAGE_CHARS = 100_000


class CompletionRequest(BaseModel):
    """Caller-provided conversation and generation options for the model."""

    messages: list[ChatMessage] = Field(
        description="Conversation messages passed through to the configured model.",
        examples=[[{"role": "user", "content": "Say hello in one short sentence."}]],
        min_length=1,
        max_length=MAX_MESSAGES,
    )
    temperature: float = Field(
        default=0.2,
        ge=0,
        le=2,
        description="Sampling temperature from 0 (most deterministic) to 2 (most varied).",
        examples=[0.2],
    )
    max_output_tokens: int | None = Field(
        default=None,
        ge=1,
        description="Optional reply limit; when omitted, the configured model default is used.",
        examples=[256],
    )

    @model_validator(mode="after")
    def _message_content_fits_limits(self) -> "CompletionRequest":
        """Bound individual and total message text without including it in errors."""
        if any(len(message.content) > MAX_MESSAGE_CHARS for message in self.messages):
            raise ValueError(f"each message must be at most {MAX_MESSAGE_CHARS} characters")
        total_characters = sum(len(message.content) for message in self.messages)
        if total_characters > MAX_TOTAL_MESSAGE_CHARS:
            raise ValueError(
                f"combined message content must be at most {MAX_TOTAL_MESSAGE_CHARS} characters"
            )
        return self


class CompletionResponse(BaseModel):
    """Model reply and provider-reported usage, with the API call duration."""

    text: str = Field(
        description="The reply text, exactly as the model returned it.",
        examples=["Hello!"],
    )
    model: str = Field(
        description="Model name reported by the provider.",
        examples=["openai/gpt-oss-20b"],
    )
    finish_reason: str | None = Field(
        description="Why generation stopped, when the provider reported a reason.",
        examples=["stop"],
    )
    prompt_tokens: int | None = Field(
        description="Provider-reported prompt token count, when available.",
        examples=[78],
    )
    completion_tokens: int | None = Field(
        description="Provider-reported reply token count, when available.",
        examples=[87],
    )
    elapsed_ms: int = Field(
        ge=0,
        description="Elapsed time for the model call in milliseconds.",
        examples=[600],
    )


class ErrorDetail(BaseModel):
    """Stable error information returned to API callers."""

    code: str = Field(
        description="Stable machine-readable error identifier.",
        examples=["llm_timeout"],
    )
    message: str = Field(
        description="Developer-oriented message that contains no prompt or secret values.",
        examples=["The model server did not answer within the time limit."],
    )
    retryable: bool = Field(
        description="Whether retrying the same request may succeed.",
        examples=[True],
    )
    details: dict[str, Any] = Field(
        description="Structured error-specific information, when available.",
        examples=[{"estimated_tokens": 9000, "budget_tokens": 7168}],
    )


class ErrorResponse(BaseModel):
    """Shared error envelope for API failures."""

    error: ErrorDetail = Field(
        description="The error code, safe message, retryability, and optional details.",
        examples=[
            {
                "code": "llm_timeout",
                "message": "The model server did not answer within the time limit.",
                "retryable": True,
                "details": {},
            }
        ],
    )


class ModelInfoResponse(BaseModel):
    """Non-secret model configuration exposed by the developer model-info route."""

    model: str = Field(
        description="Configured model identifier.",
        examples=["openai/gpt-oss-20b"],
    )
    host: str = Field(
        description="Provider host from the configured base URL, without its path.",
        examples=["api.groq.com"],
    )
    context_tokens: int = Field(
        description="Configured context window in tokens.",
        examples=[8192],
    )
    max_output_tokens: int = Field(
        description="Configured maximum output size in tokens.",
        examples=[1024],
    )
    api_key_set: bool = Field(
        description="Whether a provider API key is configured; the key is never returned.",
        examples=[True],
    )
