from typing import Self
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """Which language model to use and how to reach it, read from environment variables.

    Each field is read from the variable named after it with an `LLM_` prefix, for
    example `base_url` from `LLM_BASE_URL`. Real environment variables win over a
    `.env` file. The `.env` file is looked for in the current folder and, so that it
    also works when the API is started from `apps/api`, two folders up. Empty
    variables count as not set.
    """

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        # Later files win, so a .env in the current folder beats the one at the repo root.
        env_file=("../../.env", ".env"),
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        str_strip_whitespace=True,
    )

    base_url: str = Field(
        description=(
            "Address of an OpenAI-compatible API, including the /v1 part. The gateway adds /chat/completions to it. A trailing slash is removed."
        ),
        min_length=1,
        examples=["http://localhost:11434/v1"],
    )
    model: str = Field(
        description="Name of the model to use, exactly as the provider lists it.",
        min_length=1,
        examples=["llama3.1:8b"],
    )
    api_key: SecretStr | None = Field(
        default=None,
        description=(
            "Secret key for the provider. Locally hosted models need none. It is never shown in logs or in the printed settings."
        ),
        examples=["your-api-key"],
    )
    context_tokens: int = Field(
        default=8192,
        ge=512,
        description=(
            "How many tokens the model can handle in one request, prompt and reply together. Take it from the model's documentation."
        ),
        examples=[8192],
    )
    max_output_tokens: int = Field(
        default=1024,
        ge=1,
        description=(
            "The longest reply to ask for, in tokens. This much room is kept free in the "
            "context window when checking that a prompt fits."
        ),
        examples=[1024],
    )
    timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        description="How long to wait for the provider to answer before giving up, in seconds.",
        examples=[60],
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description=(
            "How many extra attempts to make after a temporary failure such as a timeout or "
            "a busy server. Use 0 to never retry."
        ),
        examples=[2],
    )

    @field_validator("base_url")
    @classmethod
    def _clean_base_url(cls, value: str) -> str:
        """Require a full http or https address and drop any trailing slash."""
        value = value.rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be a full address starting with http:// or https://")
        return value

    @model_validator(mode="after")
    def _reply_must_fit_in_the_context(self) -> Self:
        """Require room in the context window for both a prompt and the longest reply."""
        if self.max_output_tokens >= self.context_tokens:
            raise ValueError(
                "max_output_tokens must be smaller than context_tokens, "
                "so there is room left for the prompt"
            )
        return self
