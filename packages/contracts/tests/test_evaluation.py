from typing import Any

import pytest
from contracts.evaluation import Evaluation, MetricScore
from pydantic import ValidationError

METRICS = ["correctness", "depth", "clarity", "relevance"]


QUESTION_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"


def valid_evaluation_data() -> dict[str,Any]:
    """A fresh, valid evaluation as a dictionary, for tests to modify."""
    data: dict[str,Any] = {"question_id": QUESTION_ID, "summary": "Solid answer overall."}
    for metric in METRICS:
        data[metric] = {"score": 7, "feedback": "Reasonable."}
    return data


@pytest.mark.parametrize("score", [0, 1, 5, 10])
def test_metric_score_accepts_scores_in_range(score):
    """Scores from 0 to 10 inclusive are valid, including both edges."""
    result = MetricScore.model_validate({"score": score, "feedback": "Fine."})
    assert result.score == score


@pytest.mark.parametrize("score", [-1, 11, 100])
def test_metric_score_rejects_scores_out_of_range(score):
    """Scores below 0 or above 10 are invalid."""
    with pytest.raises(ValidationError):
        MetricScore.model_validate({"score": score, "feedback": "Fine."})


def test_metric_score_rejects_fractional_scores():
    """Scores are whole numbers, so 7.5 is invalid."""
    with pytest.raises(ValidationError):
        MetricScore.model_validate({"score": 7.5, "feedback": "Fine."})


@pytest.mark.parametrize("blank", ["", "   "])
def test_metric_score_rejects_blank_feedback(blank):
    """Every score must come with a written explanation."""
    with pytest.raises(ValidationError):
        MetricScore.model_validate({"score": 5, "feedback": blank})


def test_evaluation_accepts_valid_values():
    """An evaluation with an id, four scored metrics, and a summary is valid."""
    evaluation = Evaluation.model_validate(valid_evaluation_data())
    assert evaluation.correctness.score == 7


@pytest.mark.parametrize("metric", METRICS)
def test_evaluation_requires_every_metric(metric):
    """All four metrics must be scored."""
    data = valid_evaluation_data()
    del data[metric]
    with pytest.raises(ValidationError):
        Evaluation.model_validate(data)


def test_evaluation_rejects_blank_summary():
    """The summary cannot be blank."""
    data = valid_evaluation_data()
    data["summary"] = "   "
    with pytest.raises(ValidationError):
        Evaluation.model_validate(data)


@pytest.mark.parametrize("bad_id", ["", "q-1"])
def test_evaluation_rejects_invalid_question_id(bad_id):
    """The question id must be a valid UUID."""
    data = valid_evaluation_data()
    data["question_id"] = bad_id
    with pytest.raises(ValidationError):
        Evaluation.model_validate(data)


def test_evaluation_names_the_failing_metric():
    """A bad score inside one metric is reported with the exact path to it."""
    data = valid_evaluation_data()
    data["depth"]["score"] = 11
    with pytest.raises(ValidationError) as exc_info:
        Evaluation.model_validate(data)
    assert exc_info.value.errors()[0]["loc"] == ("depth", "score")