import llm_gateway
import pytest
from pydantic import BaseModel

EXPECTED_PUBLIC_NAMES = {
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
}

EXPORTED = [getattr(llm_gateway, name) for name in llm_gateway.__all__]
PUBLIC_CLASSES = [item for item in EXPORTED if isinstance(item, type)]
PUBLIC_MODELS = [item for item in PUBLIC_CLASSES if issubclass(item, BaseModel)]


def test_public_names_are_exactly_the_expected_ones():
    """The public API changes only on purpose: adding or removing an exported name means updating this list."""
    assert set(llm_gateway.__all__) == EXPECTED_PUBLIC_NAMES


@pytest.mark.parametrize("item", PUBLIC_CLASSES, ids=lambda item: item.__name__)
def test_every_public_class_has_a_docstring(item):
    """Every public model and error has its own docstring, so generated documentation is never empty."""
    assert item.__doc__ is not None
    assert item.__doc__.strip() != ""


@pytest.mark.parametrize("model", PUBLIC_MODELS, ids=lambda model: model.__name__)
def test_every_public_model_field_has_a_description(model):
    """Every field of every public model has a description, so generated documentation has no gaps."""
    undocumented = [name for name, field in model.model_fields.items() if not field.description]
    assert undocumented == []
