import pytest
from llm_gateway import (
    ChatMessage,
    ContextBudgetExceededError,
    check_context_budget,
    estimate_prompt_tokens,
    estimate_tokens,
)


def user(text: str) -> ChatMessage:
    """Build a user message holding the given text."""
    return ChatMessage(role="user", content=text)


def test_empty_text_takes_no_tokens():
    """Nothing written means nothing to count."""
    assert estimate_tokens("") == 0


@pytest.mark.parametrize(("length", "expected"), [(1, 1), (3, 1), (4, 2), (30, 10)])
def test_plain_ascii_counts_as_a_third_of_a_token_per_character_rounded_up(length, expected):
    """ASCII text is counted at three characters per token, rounding up."""
    assert estimate_tokens("a" * length) == expected


def test_every_non_ascii_character_counts_as_a_whole_token():
    """Devanagari and other non-ASCII characters count one token each, because they tokenize poorly."""
    assert estimate_tokens("नमस्ते") == 6


def test_mixed_text_adds_both_kinds():
    """Text with both kinds of characters is counted as ASCII part plus one token per other character."""
    assert estimate_tokens("ab" + "न") == 2


def test_the_estimate_is_never_below_a_plain_four_characters_per_token_guess():
    """The estimate leans high: it is at least what the usual English rule of thumb would give."""
    sentence = "React decides to re-render a component when its state or props change. " * 20
    assert estimate_tokens(sentence) >= len(sentence) / 4


def test_each_message_adds_a_little_overhead():
    """Every message costs its own text plus a few tokens for the role label."""
    assert estimate_prompt_tokens([user("a" * 3)]) == 1 + 4
    assert estimate_prompt_tokens([user("a" * 3), user("a" * 3)]) == 2 * (1 + 4)


def test_a_conversation_that_fits_passes_and_returns_the_estimate():
    """A prompt within the budget is accepted, and the check hands back its estimated size."""
    messages = [user("a" * 300)]
    assert check_context_budget(messages, context_tokens=1000, max_output_tokens=200) == 104


def test_a_prompt_exactly_at_the_budget_is_accepted():
    """Using every token of the budget is allowed; only going over is an error."""
    messages = [user("a" * 300)]  # estimated at 104 tokens
    assert check_context_budget(messages, context_tokens=304, max_output_tokens=200) == 104


def test_a_prompt_one_token_over_the_budget_is_rejected():
    """One token over the budget is an error."""
    messages = [user("a" * 300)]  # estimated at 104 tokens
    with pytest.raises(ContextBudgetExceededError):
        check_context_budget(messages, context_tokens=303, max_output_tokens=200)


def test_room_for_the_reply_is_taken_out_of_the_budget():
    """A longer allowed reply leaves less room for the prompt."""
    messages = [user("a" * 300)]
    check_context_budget(messages, context_tokens=1000, max_output_tokens=100)
    with pytest.raises(ContextBudgetExceededError):
        check_context_budget(messages, context_tokens=1000, max_output_tokens=900)


def test_the_error_reports_the_estimate_and_the_budget():
    """The error carries both numbers and states them in its message."""
    with pytest.raises(ContextBudgetExceededError) as caught:
        check_context_budget([user("a" * 300)], context_tokens=1000, max_output_tokens=900)
    assert caught.value.estimated_tokens == 104
    assert caught.value.budget_tokens == 100
    assert "104" in str(caught.value)
    assert "100" in str(caught.value)


def test_the_error_never_contains_the_prompt_text():
    """The prompt may hold a resume or an answer, so it must not leak into an error message."""
    secret = "MY-PRIVATE-RESUME-TEXT " * 50
    with pytest.raises(ContextBudgetExceededError) as caught:
        check_context_budget([user(secret)], context_tokens=600, max_output_tokens=500)
    assert "PRIVATE" not in str(caught.value)


def test_a_full_job_description_and_resume_do_not_fit_the_default_window():
    """At their maximum length, a job description and resume are too big for an 8192-token window, so they must be condensed first."""
    messages = [user("a" * 20_000), user("a" * 20_000)]
    with pytest.raises(ContextBudgetExceededError):
        check_context_budget(messages, context_tokens=8192, max_output_tokens=1024)
