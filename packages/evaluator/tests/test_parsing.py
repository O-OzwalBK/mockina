import math
from typing import Any

import pytest
from contracts import Question
from evaluator.parsing import (
    FAILURE_FEEDBACK_TOO_LONG,
    FAILURE_INVALID_JSON_SHAPE,
    FAILURE_INVALID_SCORE,
    FAILURE_MISSING_FEEDBACK,
    FAILURE_MISSING_METRIC,
    FAILURE_MISSING_SCORE,
    FAILURE_MISSING_SUMMARY,
    FAILURE_SUMMARY_TOO_LONG,
    EvaluationReplyError,
    read_evaluation,
)

QUESTION_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
METRICS = ("correctness", "depth", "clarity", "relevance")


def _question() -> Question:
    """A question whose id the evaluation must carry."""
    return Question(
        id=QUESTION_ID,
        text="How does React decide when to re-render a component?",
        skill_id="react-rendering",
        difficulty=3,
    )


def valid_data() -> dict[str, Any]:
    """A fresh, valid evaluation reply body."""
    data: dict[str, Any] = {"summary": "Solid answer overall."}
    for metric in METRICS:
        data[metric] = {"score": 7, "feedback": "Reasonable."}
    return data


def test_a_valid_reply_becomes_an_evaluation_with_the_questions_id():
    """The server's question id is stored even though the model never supplies one."""
    evaluation = read_evaluation(valid_data(), _question())
    assert evaluation.question_id == _question().id
    assert evaluation.correctness.score == 7


def test_an_id_from_the_model_is_ignored():
    """A model cannot change which question the evaluation grades."""
    data = valid_data()
    data["question_id"] = "00000000-0000-0000-0000-000000000000"
    assert read_evaluation(data, _question()).question_id == _question().id


def test_extra_keys_from_the_model_are_ignored():
    """Extra keys do not fail an otherwise valid grade."""
    data = valid_data()
    data["overall"] = 9
    data["correctness"]["confidence"] = 0.9
    evaluation = read_evaluation(data, _question())
    assert evaluation.correctness.score == 7
    assert not hasattr(evaluation, "overall")


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (7, 7),
        ("7", 7),
        ("7/10", 7),
        ("7 out of 10", 7),
        (7.5, 8),
        (7.4, 7),
        ("7.5", 8),
        (0, 0),
        (10, 10),
        (10.0, 10),
    ],
)
def test_scores_are_normalized_to_whole_numbers(score, expected):
    """Integer and numeric scores become whole numbers, with fractions rounded half up."""
    data = valid_data()
    data["correctness"]["score"] = score
    assert read_evaluation(data, _question()).correctness.score == expected


@pytest.mark.parametrize("score", [11, -1, 10.5, -0.1, "11/10", "not a score", True, None])
def test_invalid_scores_are_rejected(score):
    """Out-of-range, non-numeric, and boolean scores are model mistakes, not clamped."""
    data = valid_data()
    data["correctness"]["score"] = score
    with pytest.raises(EvaluationReplyError) as caught:
        read_evaluation(data, _question())
    assert FAILURE_INVALID_SCORE in caught.value.failures


def test_non_finite_scores_are_rejected():
    """NaN and infinity cannot become an integer score."""
    for score in (math.nan, math.inf, -math.inf):
        data = valid_data()
        data["correctness"]["score"] = score
        with pytest.raises(EvaluationReplyError):
            read_evaluation(data, _question())


@pytest.mark.parametrize("metric", METRICS)
def test_a_missing_metric_is_named(metric):
    """Every metric is required."""
    data = valid_data()
    del data[metric]
    with pytest.raises(EvaluationReplyError) as caught:
        read_evaluation(data, _question())
    assert FAILURE_MISSING_METRIC in caught.value.failures


@pytest.mark.parametrize("metric", METRICS)
def test_a_missing_score_is_named(metric):
    """Every metric must carry a score."""
    data = valid_data()
    del data[metric]["score"]
    with pytest.raises(EvaluationReplyError) as caught:
        read_evaluation(data, _question())
    assert FAILURE_MISSING_SCORE in caught.value.failures


@pytest.mark.parametrize("metric", METRICS)
@pytest.mark.parametrize("feedback", [None, "", "   "])
def test_missing_or_blank_feedback_is_named(metric, feedback):
    """Every metric must carry nonblank feedback."""
    data = valid_data()
    data[metric]["feedback"] = feedback
    with pytest.raises(EvaluationReplyError) as caught:
        read_evaluation(data, _question())
    assert FAILURE_MISSING_FEEDBACK in caught.value.failures


@pytest.mark.parametrize("summary", [None, "", "   "])
def test_a_missing_or_blank_summary_is_named(summary):
    """The overall summary cannot be empty."""
    data = valid_data()
    data["summary"] = summary
    with pytest.raises(EvaluationReplyError) as caught:
        read_evaluation(data, _question())
    assert FAILURE_MISSING_SUMMARY in caught.value.failures


def test_feedback_over_the_contract_limit_is_named():
    """A too-long feedback field is a repairable reply, not a crash."""
    data = valid_data()
    data["correctness"]["feedback"] = "a" * 1_001
    with pytest.raises(EvaluationReplyError) as caught:
        read_evaluation(data, _question())
    assert FAILURE_FEEDBACK_TOO_LONG in caught.value.failures


def test_summary_over_the_contract_limit_is_named():
    """A too-long summary is a repairable reply."""
    data = valid_data()
    data["summary"] = "a" * 2_001
    with pytest.raises(EvaluationReplyError) as caught:
        read_evaluation(data, _question())
    assert FAILURE_SUMMARY_TOO_LONG in caught.value.failures


@pytest.mark.parametrize("data", [None, [], "text"])
def test_a_reply_that_is_not_the_expected_object_is_rejected(data):
    """A non-object or a body without all metrics is a repairable shape failure."""
    with pytest.raises(EvaluationReplyError) as caught:
        read_evaluation(data, _question())
    assert FAILURE_INVALID_JSON_SHAPE in caught.value.failures


def test_the_error_message_does_not_echo_the_model_text():
    """A parse failure names checks only, never the reply or feedback text."""
    marker = "private-feedback-marker"
    data = valid_data()
    data["correctness"]["feedback"] = marker
    data["correctness"]["score"] = "bad-score-marker"
    with pytest.raises(EvaluationReplyError) as caught:
        read_evaluation(data, _question())
    assert marker not in str(caught.value)
    assert "bad-score-marker" not in str(caught.value)
