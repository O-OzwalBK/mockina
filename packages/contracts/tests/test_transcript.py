import pytest
from pydantic import ValidationError

from contracts.transcript import Answer, WordTiming

# WordTiming model tests


def test_word_timing_accepts_valid_values():
    """A word with text and non-negative start and end is valid and keeps its values."""
    timing = WordTiming(word="hello", start=0.0, end=0.4)
    assert timing.word == "hello"
    assert timing.start == 0.0
    assert timing.end == 0.4


@pytest.mark.parametrize("good_start_timestamp", [0, 0.0, 0.001, 3600.5])
def test_word_timing_accepts_non_negative_start(good_start_timestamp):
    """A word with non-negative start timestamp is valid"""
    timing = WordTiming(word="hi", start=good_start_timestamp, end=4000.0)
    assert timing.start == good_start_timestamp

@pytest.mark.parametrize("bad_start_timestamp", [-0.001, -1, -1000])
def test_word_timing_rejects_negative_start_time_for_word(bad_start_timestamp):
    """A word cannot start before the answer begins (start must be >= 0)."""
    with pytest.raises(ValidationError):
        WordTiming(word="hi", start=bad_start_timestamp, end=0.4)


def test_word_timing_rejects_negative_end_time_for_word():
    """A word cannot end before the answer begins (end must be >= 0)."""
    with pytest.raises(ValidationError):
        WordTiming(word="hi", start=0.0, end=-0.1)


def test_word_timing_requires_word():
    """A timing without the word text is invalid."""
    with pytest.raises(ValidationError):
        WordTiming(start=0.0, end=0.4)  # type: ignore[call-arg]


# Answer model tests


def test_answer_accepts_valid_values():
    """An answer with a transcript, word timings, and a duration is valid."""
    answer = Answer(
        transcript="hello there",
        words=[
            WordTiming(word="hello", start=0.0, end=0.4),
            WordTiming(word="there", start=0.5, end=0.9),
        ],
        duration=1.2,
    )
    assert len(answer.words) == 2
    assert answer.words[1].word == "there"


def test_answer_words_default_to_empty_list():
    """Word timings are optional, so an answer from a speech-to-text source without them is valid."""
    answer = Answer(transcript="hi", duration=1.0)
    assert answer.words == []


def test_answer_default_lists_are_not_shared():
    """Each answer gets its own words list, so editing one never changes another."""
    first = Answer(transcript="a", duration=1.0)
    second = Answer(transcript="b", duration=1.0)
    assert first.words is not second.words


def test_answer_allows_empty_transcript():
    """A silent answer (empty transcript) is valid."""
    answer = Answer(transcript="", duration=5.0)
    assert answer.transcript == ""


def test_answer_rejects_negative_duration():
    """Duration cannot be negative."""
    with pytest.raises(ValidationError):
        Answer(transcript="hi", duration=-1)


def test_answer_requires_duration():
    """Duration is required."""
    with pytest.raises(ValidationError):
        Answer(transcript="hi") # type: ignore[call-arg]


def test_answer_rejects_bad_timing_inside_words():
    """An invalid word timing inside an answer is rejected, and the error points at the exact field."""
    with pytest.raises(ValidationError) as exc_info:
        Answer(
            transcript="hi",
            words=[{"word": "hi", "start": -1, "end": 0.4}],    # type: ignore[call-arg]
            duration=1.0,
        )
    # The error should point at exactly which field of which word failed.
    assert exc_info.value.errors()[0]["loc"] == ("words", 0, "start")