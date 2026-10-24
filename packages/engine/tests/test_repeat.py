from contracts import Question
from engine.repeat import (
    EXACT_REPEAT,
    OVERLAP_REPEAT,
    REPEAT_STOPWORDS,
    REPEAT_THRESHOLD,
    content_tokens,
    find_repeat,
)

NEGATIONS = ("not", "no", "never", "without", "except", "neither", "nor")


def _question(text: str, skill_id: str = "hooks") -> Question:
    """An earlier question with the given text and skill."""
    return Question(text=text, skill_id=skill_id, difficulty=2)


def test_the_overlap_threshold_is_pinned_at_six_tenths():
    """The word-overlap threshold is the agreed 0.6, not a value a caller can drift."""
    assert REPEAT_THRESHOLD == 0.6


def test_an_exact_match_after_normalization_is_a_repeat_across_skills():
    """Case and punctuation do not hide a copy, even when the skill changed."""
    earlier = [_question("What is a closure?", skill_id="javascript")]
    match = find_repeat("what is a closure", earlier, skill_id="react")
    assert match is not None
    assert match.kind == EXACT_REPEAT
    assert match.earlier_question == "What is a closure?"


def test_word_overlap_is_a_repeat_within_one_skill():
    """A reworded question for the same skill is caught by the overlap check."""
    earlier = [
        _question("Explain how React state updates trigger re-renders in components.", "hooks")
    ]
    match = find_repeat(
        "How do React components update state and trigger re-renders?", earlier, skill_id="hooks"
    )
    assert match is not None
    assert match.kind == OVERLAP_REPEAT


def test_word_overlap_across_different_skills_is_not_a_repeat():
    """Similar wording about another skill is a different question."""
    earlier = [
        _question("Explain how React state updates trigger re-renders in components.", "routing")
    ]
    match = find_repeat(
        "How do React components update state and trigger re-renders?", earlier, skill_id="hooks"
    )
    assert match is None


def test_overlap_is_skipped_when_either_question_has_fewer_than_three_content_words():
    """Very short questions are compared exactly only, so shared filler cannot flag them."""
    earlier = [_question("React", "hooks")]
    match = find_repeat("What about React?", earlier, skill_id="hooks")
    assert match is None


def test_exact_matching_still_works_with_few_content_words():
    """The minimum word count applies to overlap only; an exact copy is always a repeat."""
    earlier = [_question("What about React?", "hooks")]
    match = find_repeat("what about react", earlier, skill_id="hooks")
    assert match is not None
    assert match.kind == EXACT_REPEAT


def test_negations_are_kept_as_content_words():
    """A negation is never a stopword, so opposite questions do not collapse together."""
    for negation in NEGATIONS:
        assert negation not in REPEAT_STOPWORDS
    assert "not" in content_tokens("Why not use a closure for callbacks?")


def test_questions_that_differ_by_a_negation_are_not_repeats():
    """One question saying not to do something is not a repeat of one saying to do it."""
    earlier = [_question("Why use a closure for callbacks?", "hooks")]
    match = find_repeat("Why not use a closure for callbacks?", earlier, skill_id="hooks")
    assert match is None


def test_low_word_overlap_is_not_a_repeat():
    """Sharing one word out of five is below the threshold."""
    earlier = [_question("Explain React routing and effects.", "hooks")]
    match = find_repeat("Describe React state and hooks.", earlier, skill_id="hooks")
    assert match is None
