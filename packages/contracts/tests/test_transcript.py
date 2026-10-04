from typing import Any

import pytest
from contracts.transcript import (
    MAX_ANSWER_DURATION_SECONDS,
    MAX_TRANSCRIPT_LENGTH,
    MAX_WORD_LENGTH,
    MAX_WORDS_PER_ANSWER,
    Answer,
    WordTiming,
)
from pydantic import ValidationError


def word(start: float, end: float, text: str = "hi") -> dict[str, Any]:
    """A word timing as a dictionary."""
    return {"word": text, "start": start, "end": end}


def answer_data(**overrides: Any) -> dict[str, Any]:
    """A fresh, valid answer as a dictionary, with any given fields replaced."""
    data: dict[str, Any] = {"transcript": "hello there", "duration": 1.0}
    data.update(overrides)
    return data

# WordTiming model tests


def test_word_timing_accepts_valid_values():
    """A word with text and non-negative start and end is valid and keeps its values."""
    timing = WordTiming(word="hello", start=0.1, end=0.4)
    assert timing.word == "hello"
    assert timing.start == 0.1
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


@pytest.mark.parametrize("field", ["start", "end"])
@pytest.mark.parametrize("bad", [float("inf"), float("nan")])
def test_word_timing_rejects_non_finite_times(field, bad):
    """Infinite and not-a-number times are invalid."""
    data = word(0.0, 0.4)
    data[field] = bad
    with pytest.raises(ValidationError):
        WordTiming.model_validate(data)


def test_word_timing_accepts_maximum_word_length():
    """A word exactly at the length limit is valid."""
    WordTiming.model_validate(word(0.0, 0.4, "a" * MAX_WORD_LENGTH))


def test_word_timing_rejects_overlong_word():
    """A word one character over the length limit is invalid."""
    with pytest.raises(ValidationError):
        WordTiming.model_validate(word(0.0, 0.4, "a" * (MAX_WORD_LENGTH + 1)))


def test_word_timing_is_immutable():
    """A word timing cannot be changed after creation."""
    timing = WordTiming.model_validate(word(0.0, 0.4))
    with pytest.raises(ValidationError):
        timing.word = "changed"
        
# Answer model tests


def test_answer_accepts_valid_values():
    """An answer with a transcript, word timings, and a duration is valid."""
    answer = Answer.model_validate(
        answer_data(words=[word(0.0, 0.4, "hello"), word(0.5, 0.9, "there")], duration=1.2)
    )
    assert len(answer.words) == 2
    assert answer.words[1].word == "there"


def test_answer_words_default_to_empty_tuple():
    """Word timings are optional, so an answer from a speech-to-text source without them is valid."""
    answer = Answer(transcript="hi", duration=1.0)
    assert answer.words == ()


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


def test_answer_accepts_maximum_transcript_length():
    """A transcript exactly at the length limit is valid."""
    Answer.model_validate(answer_data(transcript="a" * MAX_TRANSCRIPT_LENGTH))


def test_answer_rejects_overlong_transcript():
    """A transcript one character over the length limit is invalid."""
    with pytest.raises(ValidationError):
        Answer.model_validate(answer_data(transcript="a" * (MAX_TRANSCRIPT_LENGTH + 1)))


def test_answer_accepts_maximum_word_count():
    """An answer with exactly the maximum number of words is valid."""
    Answer.model_validate(answer_data(words=[word(0.0, 0.1)] * MAX_WORDS_PER_ANSWER))


def test_answer_rejects_too_many_words():
    """An answer with one word more than the maximum is invalid."""
    with pytest.raises(ValidationError):
        Answer.model_validate(answer_data(words=[word(0.0, 0.1)] * (MAX_WORDS_PER_ANSWER + 1)))


def test_answer_accepts_maximum_duration():
    """A duration exactly at the limit is valid."""
    Answer.model_validate(answer_data(duration=MAX_ANSWER_DURATION_SECONDS))


def test_answer_rejects_duration_over_maximum():
    """A duration over the limit is invalid."""
    with pytest.raises(ValidationError):
        Answer.model_validate(answer_data(duration=MAX_ANSWER_DURATION_SECONDS + 1))


@pytest.mark.parametrize("bad", [float("inf"), float("nan")])
def test_answer_rejects_non_finite_duration(bad):
    """An infinite or not-a-number duration is invalid."""
    with pytest.raises(ValidationError):
        Answer.model_validate(answer_data(duration=bad))


def test_answer_accepts_overlapping_words_in_order():
    """Words may overlap slightly, as speech-to-text timings often do; only the order of their start times matters."""
    Answer.model_validate(answer_data(words=[word(0.0, 0.5, "hello"), word(0.4, 0.9, "there")]))


def test_answer_rejects_words_out_of_order():
    """Words must be listed in the order they were spoken."""
    with pytest.raises(ValidationError):
        Answer.model_validate(answer_data(words=[word(1.0, 1.4), word(0.0, 0.4)]))


def test_answer_words_are_a_tuple():
    """Words are stored as a tuple, so they cannot be appended to in place."""
    answer = Answer.model_validate(answer_data(words=[word(0.0, 0.4)]))
    assert isinstance(answer.words, tuple)


def test_answer_is_immutable():
    """An answer cannot be changed after creation."""
    answer = Answer.model_validate(answer_data())
    with pytest.raises(ValidationError):
        answer.transcript = "changed"