from typing import Literal

from contracts import ImmutableModel
from pydantic import Field

Role = Literal["system", "user", "assistant"]


class ChatMessage(ImmutableModel):
    """One message in a conversation with the language model."""

    role: Role = Field(
        description=(
            "Who wrote the message: 'system' for standing instructions, 'user' for the "
            "question or task, 'assistant' for an earlier reply from the model."
        ),
        examples=["user"],
    )
    content: str = Field(
        description="The text of the message.",
        min_length=1,
        examples=["Grade this answer on correctness, depth, clarity, and relevance."],
    )


class Completion(ImmutableModel):
    """The model's reply to a conversation, with the details the provider reported."""

    text: str = Field(
        description="The reply text, exactly as the model wrote it.",
        min_length=1,
        examples=["Strong fundamentals; next time, mention how keys affect list updates."],
    )
    model: str = Field(
        description="Name of the model that produced the reply, as the provider reported it.",
        min_length=1,
        examples=["llama-3.1-8b-instruct"],
    )
    finish_reason: str | None = Field(
        default=None,
        description=(
            "Why the model stopped writing: 'stop' means it finished, 'length' means it "
            "was cut off at the output limit. None when the provider did not say."
        ),
        examples=["stop"],
    )
    prompt_tokens: int | None = Field(
        default=None,
        ge=0,
        description="Tokens the provider counted in the prompt, or None if it did not report them.",
        examples=[412],
    )
    completion_tokens: int | None = Field(
        default=None,
        ge=0,
        description="Tokens the provider counted in the reply, or None if it did not report them.",
        examples=[85],
    )
