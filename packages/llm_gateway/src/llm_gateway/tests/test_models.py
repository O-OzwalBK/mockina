import pytest
from llm_gateway import ChatMessage, Completion
from pydantic import ValidationError


def test_chat_message_accepts_each_role():
    """A message can come from the system, the user, or the assistant."""
    for role in ("system", "user", "assistant"):
        assert ChatMessage(role=role, content="Hello").role == role


def test_chat_message_rejects_an_unknown_role():
    """Any role other than system, user, or assistant is rejected."""
    with pytest.raises(ValidationError):
        ChatMessage.model_validate({"role": "robot", "content": "Hello"})


def test_chat_message_rejects_empty_content():
    """A message with no text is rejected, because providers refuse empty messages."""
    with pytest.raises(ValidationError):
        ChatMessage.model_validate({"role": "user", "content": ""})


def test_chat_message_rejects_whitespace_only_content():
    """Text that is only spaces counts as empty after surrounding whitespace is stripped."""
    with pytest.raises(ValidationError):
        ChatMessage.model_validate({"role": "user", "content": "   \n "})


def test_chat_message_strips_surrounding_whitespace():
    """Spaces and newlines around the text are removed."""
    assert ChatMessage(role="user", content="  Hello\n").content == "Hello"


def test_chat_message_rejects_unknown_fields():
    """A misspelled or extra field is an error, not silently ignored."""
    with pytest.raises(ValidationError):
        ChatMessage.model_validate({"role": "user", "content": "Hi", "name": "Oozy"})


def test_chat_message_cannot_be_changed():
    """A message is frozen once created."""
    message = ChatMessage(role="user", content="Hello")
    with pytest.raises(ValidationError):
        setattr(message, "content", "Goodbye")


def test_completion_needs_only_text_and_model():
    """The token counts and finish reason are optional and default to None."""
    completion = Completion(text="Well done.", model="llama-3.1-8b-instruct")
    assert completion.finish_reason is None
    assert completion.prompt_tokens is None
    assert completion.completion_tokens is None


def test_completion_keeps_everything_the_provider_reported():
    """Finish reason and token counts are stored when the provider gives them."""
    completion = Completion(
        text="Well done.",
        model="llama-3.1-8b-instruct",
        finish_reason="length",
        prompt_tokens=412,
        completion_tokens=85,
    )
    assert completion.finish_reason == "length"
    assert completion.prompt_tokens == 412
    assert completion.completion_tokens == 85


def test_completion_rejects_empty_text():
    """A reply with no text is rejected, because nothing downstream can use it."""
    with pytest.raises(ValidationError):
        Completion.model_validate({"text": "", "model": "llama-3.1-8b-instruct"})


def test_completion_rejects_an_empty_model_name():
    """The model name must not be empty."""
    with pytest.raises(ValidationError):
        Completion.model_validate({"text": "Well done.", "model": ""})


@pytest.mark.parametrize("field", ["prompt_tokens", "completion_tokens"])
def test_completion_rejects_negative_token_counts(field):
    """Token counts cannot be negative."""
    with pytest.raises(ValidationError):
        Completion.model_validate({"text": "Well done.", "model": "m", field: -1})


def test_completion_cannot_be_changed():
    """A completion is frozen once created."""
    completion = Completion(text="Well done.", model="m")
    with pytest.raises(ValidationError):
        setattr(completion, "text", "Changed")
