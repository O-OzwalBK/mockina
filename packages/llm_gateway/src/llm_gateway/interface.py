from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from llm_gateway.models import ChatMessage, Completion


@runtime_checkable
class LLM(Protocol):
    """Anything that can turn a conversation into a model reply.

    The evaluator and the engine depend on this shape, not on one particular client, so
    tests can hand them a fake and the real client can be swapped for another one. Every
    failure is raised as an LLMError.
    """

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ) -> Completion:
        """Send the conversation to the model and return its reply.

        `max_output_tokens` caps the length of the reply for this call; None means use
        the configured default.
        """
        ...
