"""One way for the rest of the backend to talk to a language model.

This package sends a conversation to any OpenAI-compatible chat API and returns the
reply text. It does not write prompts and does not check what the model said; that
belongs to the packages that use it. Import public names from here, for example
`from llm_gateway import ChatMessage`.
"""

from llm_gateway.budget import check_context_budget, estimate_prompt_tokens, estimate_tokens
from llm_gateway.client import OpenAICompatibleLLM
from llm_gateway.errors import (
    ContextBudgetExceededError,
    LLMAuthError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMServerError,
    LLMTimeoutError,
)
from llm_gateway.interface import LLM
from llm_gateway.models import ChatMessage, Completion
from llm_gateway.retry import RetryingLLM
from llm_gateway.settings import LLMSettings

__all__ = [
    "ChatMessage",
    "Completion",
    "ContextBudgetExceededError",
    "LLM",
    "LLMAuthError",
    "LLMConnectionError",
    "LLMError",
    "LLMRateLimitError",
    "LLMRequestError",
    "LLMResponseError",
    "LLMServerError",
    "LLMSettings",
    "LLMTimeoutError",
    "OpenAICompatibleLLM",
    "RetryingLLM",
    "check_context_budget",
    "estimate_prompt_tokens",
    "estimate_tokens",
]
