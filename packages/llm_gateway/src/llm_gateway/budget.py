from collections.abc import Sequence
from math import ceil

from llm_gateway.errors import ContextBudgetExceededError
from llm_gateway.models import ChatMessage

# Plain English averages about 4 characters per token. Assuming 3 means we guess too
# many tokens rather than too few, so a prompt that passes our check will fit.
ASCII_CHARACTERS_PER_TOKEN = 3

# Every message costs a few extra tokens for its role label and separators.
TOKENS_PER_MESSAGE = 4


def estimate_tokens(text: str) -> int:
    """Estimate how many tokens a piece of text takes, leaning high on purpose.

    There is no tokenizer that works for every model, so this is a guess. Plain ASCII
    characters count as a third of a token each. Every other character (Devanagari,
    accented letters, emoji, CJK) counts as a whole token, because many tokenizers
    split such text into one or more tokens per character.
    """
    other_characters = sum(1 for character in text if ord(character) > 127)
    ascii_characters = len(text) - other_characters
    return ceil(ascii_characters / ASCII_CHARACTERS_PER_TOKEN) + other_characters


def estimate_prompt_tokens(messages: Sequence[ChatMessage]) -> int:
    """Estimate how many tokens a whole conversation takes, including per-message overhead."""
    return sum(estimate_tokens(message.content) + TOKENS_PER_MESSAGE for message in messages)


def check_context_budget(
    messages: Sequence[ChatMessage], *, context_tokens: int, max_output_tokens: int
) -> int:
    """Make sure the conversation fits in the model's context window, and return the estimate.

    The context window holds the prompt and the reply together, so room for the longest
    reply is kept free. Raises ContextBudgetExceededError if the prompt is too long. The
    error names the numbers but never includes any of the prompt text.
    """
    budget_tokens = context_tokens - max_output_tokens
    estimated_tokens = estimate_prompt_tokens(messages)
    if estimated_tokens > budget_tokens:
        raise ContextBudgetExceededError(
            f"The prompt is estimated at {estimated_tokens} tokens, but only "
            f"{budget_tokens} fit after keeping {max_output_tokens} tokens free for the reply.",
            estimated_tokens=estimated_tokens,
            budget_tokens=budget_tokens,
        )
    return estimated_tokens
