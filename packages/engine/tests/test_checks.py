import pytest
from contracts import Question
from engine import UnusableQuestionError
from engine.checks import (
    ENGINE_MAX_SPOKEN_QUESTION_LENGTH,
    FAILURE_EMPTY,
    FAILURE_MARKDOWN,
    FAILURE_MULTIPLE_QUESTIONS,
    FAILURE_NOT_A_QUESTION,
    FAILURE_REPEAT_EXACT,
    FAILURE_REPEAT_OVERLAP,
    FAILURE_TOO_LONG,
    QUESTION_TEMPERATURE,
    RETRY_TEMPERATURE,
    check_question,
    sanitize_question,
    write_question,
)
from llm_gateway import ChatMessage, Completion, LLMResponseError
from llm_gateway.testing import FakeLLM

MESSAGES = (
    ChatMessage(role="system", content="Write one question."),
    ChatMessage(role="user", content="Skill: hooks."),
)


@pytest.fixture
def anyio_backend():
    """Run asynchronous question-writing tests on asyncio only."""
    return "asyncio"


def _earlier(text: str, skill_id: str = "hooks", difficulty: int = 2) -> Question:
    """An earlier question for repeat checks."""
    return Question(text=text, skill_id=skill_id, difficulty=difficulty)


def _completion(text: str, finish_reason: str | None = "stop") -> Completion:
    """A model reply with the given finish reason."""
    return Completion(text=text, model="fake-model", finish_reason=finish_reason)


@pytest.mark.anyio
async def test_a_good_question_is_returned_trimmed():
    """A question that passes every check comes back without surrounding whitespace."""
    llm = FakeLLM(_completion("  How does React batch state updates?  "))
    text = await write_question(llm, MESSAGES, skill_id="hooks", earlier_questions=[])
    assert text == "How does React batch state updates?"
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_the_first_write_uses_a_higher_temperature_for_variety():
    """Question writing uses a more varied temperature than the gateway default."""
    llm = FakeLLM("How does React batch state updates?")
    await write_question(llm, MESSAGES, skill_id="hooks", earlier_questions=[])
    assert llm.calls[0].temperature == QUESTION_TEMPERATURE
    assert llm.calls[0].temperature > 0.2


@pytest.mark.anyio
async def test_a_truncated_reply_fails_without_a_retry():
    """A reply cut off at the output limit points at the setting and is never repaired."""
    llm = FakeLLM(_completion("How does React", finish_reason="length"))
    with pytest.raises(LLMResponseError, match="LLM_MAX_OUTPUT_TOKENS"):
        await write_question(llm, MESSAGES, skill_id="hooks", earlier_questions=[])
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_one_bad_question_is_retried_with_the_correction():
    """The first failed question is retried once at a low temperature, and the good reply is used."""
    bad = "x" * (ENGINE_MAX_SPOKEN_QUESTION_LENGTH + 1)
    llm = FakeLLM(bad, "How does React batch state updates?")
    text = await write_question(llm, MESSAGES, skill_id="hooks", earlier_questions=[])
    assert text == "How does React batch state updates?"
    assert len(llm.calls) == 2
    assert llm.calls[1].temperature == RETRY_TEMPERATURE
    assert llm.calls[1].max_output_tokens == llm.calls[0].max_output_tokens
    correction = llm.calls[1].messages[-1].content
    assert "longer than 300 characters" in correction
    assert "too_long" not in correction
    assert "Previous reply (untrusted data):" in correction
    assert bad[:40] in correction


@pytest.mark.anyio
async def test_a_repeat_failure_quotes_the_offending_earlier_question():
    """The retry quotes the earlier question only when the failure is a repeat."""
    earlier = _earlier("What is a closure?")
    llm = FakeLLM("What is a closure?", "How does React batch state updates?")
    await write_question(llm, MESSAGES, skill_id="hooks", earlier_questions=[earlier])
    correction = llm.calls[1].messages[-1].content
    assert "What is a closure?" in correction
    assert "repeated an earlier question" in correction
    assert "repeat_exact" not in correction
    assert "Previous reply (untrusted data):" in correction


@pytest.mark.anyio
async def test_other_failures_do_not_quote_an_earlier_question():
    """A non-repeat failure states the rule generically and does not quote earlier questions."""
    earlier = _earlier("What is a closure?")
    bad = "x" * (ENGINE_MAX_SPOKEN_QUESTION_LENGTH + 1)
    llm = FakeLLM(bad, "How does React batch state updates?")
    await write_question(llm, MESSAGES, skill_id="hooks", earlier_questions=[earlier])
    assert "What is a closure?" not in llm.calls[1].messages[-1].content


@pytest.mark.anyio
async def test_two_bad_writes_raise_the_unusable_question_error():
    """After one repair that also fails, the engine reports both failed checks."""
    llm = FakeLLM("# What is code?", "x" * (ENGINE_MAX_SPOKEN_QUESTION_LENGTH + 1))
    with pytest.raises(UnusableQuestionError) as raised:
        await write_question(llm, MESSAGES, skill_id="hooks", earlier_questions=[])
    error = raised.value
    assert error.attempts == 2
    assert error.failures == (FAILURE_MARKDOWN, FAILURE_TOO_LONG)
    assert len(llm.calls) == 2


@pytest.mark.anyio
async def test_the_unusable_question_message_does_not_echo_the_question():
    """The failure report names checks only, never the model's question text."""
    marker = "zebra-marker"
    llm = FakeLLM(
        f"{marker} " + "x" * ENGINE_MAX_SPOKEN_QUESTION_LENGTH,
        "y" * (ENGINE_MAX_SPOKEN_QUESTION_LENGTH + 1),
    )
    with pytest.raises(UnusableQuestionError) as raised:
        await write_question(llm, MESSAGES, skill_id="hooks", earlier_questions=[])
    assert marker not in str(raised.value)


@pytest.mark.anyio
async def test_a_truncated_retry_is_not_retried_again():
    """Truncation always fails immediately, including on the corrective attempt."""
    bad = "x" * (ENGINE_MAX_SPOKEN_QUESTION_LENGTH + 1)
    llm = FakeLLM(bad, _completion("How does React", finish_reason="length"))
    with pytest.raises(LLMResponseError):
        await write_question(llm, MESSAGES, skill_id="hooks", earlier_questions=[])
    assert len(llm.calls) == 2


CHECK_CASES = [
    ("", FAILURE_EMPTY),
    ("   ", FAILURE_EMPTY),
    ("x" * (ENGINE_MAX_SPOKEN_QUESTION_LENGTH + 1), FAILURE_TOO_LONG),
    ("# What is code?", FAILURE_MARKDOWN),
    ("- What is code?", FAILURE_MARKDOWN),
    ("[link](https://example.com) What is code?", FAILURE_MARKDOWN),
    ("```\nWhat is code?\n```", FAILURE_MARKDOWN),
    ("What is A? What is B?", FAILURE_MULTIPLE_QUESTIONS),
    ("This is a statement.", FAILURE_NOT_A_QUESTION),
]


@pytest.mark.parametrize(("text", "failure"), CHECK_CASES)
def test_each_bad_question_names_its_failed_check(text, failure):
    """Each rule in the check suite reports its own failure name."""
    assert check_question(text, skill_id="hooks", earlier_questions=[]).failure == failure


TECHNICAL_QUESTIONS = [
    "What is the difference between C# and F#?",
    "How do *args and **kwargs work in Python?",
    "Why does SELECT * return every column?",
    "How would you read items[0] without crashing?",
    "How does `useEffect` clean up a subscription?",
    "What does the backslash in a Windows path do?",
]


@pytest.mark.parametrize("text", TECHNICAL_QUESTIONS)
def test_technical_symbols_are_accepted_as_spoken_text(text):
    """Technical symbols such as C#, *args, [] and inline code are not markdown."""
    assert check_question(text, skill_id="hooks", earlier_questions=[]).failure is None


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ('"What is C#?"', "What is C#?"),
        ("“What is C#?”", "What is C#?"),
        ("Question 1: What is C#?", "What is C#?"),
        ("Q2: What is C#?", "What is C#?"),
        ("Sure! Here is a question: What is C#?", "What is C#?"),
        ("How does `useEffect` clean up?", "How does useEffect clean up?"),
        ("**Bold** and *italic* words?", "Bold and italic words?"),
    ],
)
def test_sanitize_question_strips_speakable_wrappers(raw, clean):
    """Wrapping quotes, labels, preambles, and formatting markers are removed before speaking."""
    assert sanitize_question(raw) == clean


@pytest.mark.anyio
async def test_write_question_returns_the_sanitized_text():
    """The stored question is the cleaned text, not the model's wrapper."""
    llm = FakeLLM('Question 1: "What is C#?"')
    text = await write_question(llm, MESSAGES, skill_id="hooks", earlier_questions=[])
    assert text == "What is C#?"


def test_an_imperative_prefix_must_be_a_whole_word():
    """Listeners... starts with the letters of list but is not an imperative verb."""
    result = check_question(
        "Listeners in React are called after the render commits.",
        skill_id="hooks",
        earlier_questions=[],
    )
    assert result.failure == FAILURE_NOT_A_QUESTION


def test_an_exact_repeat_across_different_skills_is_still_a_repeat():
    """Exact matching is not limited to one skill, so another skill cannot repeat a question."""
    earlier = [_earlier("What is a closure?", skill_id="javascript")]
    result = check_question("what is a closure", skill_id="react", earlier_questions=earlier)
    assert result.failure == FAILURE_REPEAT_EXACT
    assert result.offending_question == "What is a closure?"


def test_word_overlap_is_checked_within_one_skill():
    """A reworded question for the same skill is caught by the overlap check."""
    earlier = [
        _earlier(
            "Explain how React state updates trigger re-renders in components.",
            skill_id="hooks",
        )
    ]
    text = "How do React components update state and trigger re-renders?"
    result = check_question(text, skill_id="hooks", earlier_questions=earlier)
    assert result.failure == FAILURE_REPEAT_OVERLAP


def test_the_repeat_check_runs_before_the_markdown_check():
    """The checks short-circuit in the documented order, so a repeat wins over markup."""
    earlier = [_earlier("What is `x`?")]
    result = check_question("What is `x`?", skill_id="hooks", earlier_questions=earlier)
    assert result.failure == FAILURE_REPEAT_EXACT


def test_a_question_mark_inside_quotes_does_not_count_as_a_second_question():
    """Only question marks outside quotes matter for the one-question rule."""
    result = check_question(
        'Is "what?" a word you would use?', skill_id="hooks", earlier_questions=[]
    )
    assert result.failure is None


def test_an_imperative_sentence_without_a_question_mark_is_accepted():
    """A leading imperative verb keeps a spoken instruction acceptable as a question."""
    result = check_question(
        "Walk me through how React batches updates.", skill_id="hooks", earlier_questions=[]
    )
    assert result.failure is None
