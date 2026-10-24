"""Read a model reply into the shared Evaluation contract."""

import math
import re

from contracts import Evaluation, Question
from contracts.evaluation import MAX_FEEDBACK_LENGTH, MAX_SUMMARY_LENGTH
from pydantic import ValidationError

METRICS = ("correctness", "depth", "clarity", "relevance")

FAILURE_INVALID_JSON_SHAPE = "invalid_json_shape"
FAILURE_MISSING_METRIC = "missing_metric"
FAILURE_MISSING_SCORE = "missing_score"
FAILURE_INVALID_SCORE = "invalid_score"
FAILURE_MISSING_FEEDBACK = "missing_feedback"
FAILURE_FEEDBACK_TOO_LONG = "feedback_too_long"
FAILURE_MISSING_SUMMARY = "missing_summary"
FAILURE_SUMMARY_TOO_LONG = "summary_too_long"

SCORE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:/\s*10|out\s+of\s+10)?",
    re.IGNORECASE,
)


class EvaluationReplyError(ValueError):
    """A model reply could not be read as a valid Evaluation."""

    def __init__(self, failures: tuple[str, ...]) -> None:
        """Keep only safe check names, never the model's text."""
        super().__init__("The model's reply did not contain a usable evaluation.")
        self.failures = failures
        """Names of the checks the reply failed, safe to put in a repair note."""


def _normalise_score(raw: object) -> int:
    """Turn a score-like value into a whole number, rounding fractions half up.

    Out-of-range and non-numeric values raise ValueError: they are model mistakes
    to repair, not values to clamp or guess.
    """
    if isinstance(raw, bool):
        raise ValueError("a boolean is not a score")
    if isinstance(raw, int):
        value = float(raw)
    elif isinstance(raw, float):
        value = raw
    elif isinstance(raw, str):
        match = SCORE_PATTERN.fullmatch(raw.strip())
        if match is None:
            raise ValueError("not a numeric score")
        value = float(match.group(1))
    else:
        raise ValueError("not a numeric score")

    if not math.isfinite(value) or value < 0 or value > 10:
        raise ValueError("score out of range")
    return math.floor(value + 0.5)


def _read_metric(value: object) -> tuple[int, str] | str:
    """Return a normalised metric, or the safe failure name for this metric."""
    if not isinstance(value, dict):
        return FAILURE_MISSING_METRIC
    if "score" not in value:
        return FAILURE_MISSING_SCORE
    try:
        score = _normalise_score(value["score"])
    except ValueError:
        return FAILURE_INVALID_SCORE

    feedback = value.get("feedback")
    if not isinstance(feedback, str) or not feedback.strip():
        return FAILURE_MISSING_FEEDBACK
    feedback = feedback.strip()
    if len(feedback) > MAX_FEEDBACK_LENGTH:
        return FAILURE_FEEDBACK_TOO_LONG
    return score, feedback


def read_evaluation(data: object, question: Question) -> Evaluation:
    """Validate one decoded model reply into an Evaluation for this question.

    The model never controls `question_id`; the question's id is copied in. Extra
    keys are ignored. Every failure is reported by a safe check name so the caller
    can build a correction without repeating model text.
    """
    if not isinstance(data, dict):
        raise EvaluationReplyError((FAILURE_INVALID_JSON_SHAPE,))

    metrics: dict[str, dict[str, object]] = {}
    failures: list[str] = []
    for metric in METRICS:
        result = _read_metric(data.get(metric))
        if isinstance(result, str):
            failures.append(result)
            continue
        score, feedback = result
        metrics[metric] = {"score": score, "feedback": feedback}

    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        failures.append(FAILURE_MISSING_SUMMARY)
    else:
        summary = summary.strip()
        if len(summary) > MAX_SUMMARY_LENGTH:
            failures.append(FAILURE_SUMMARY_TOO_LONG)

    if failures:
        raise EvaluationReplyError(tuple(dict.fromkeys(failures)))

    payload = {
        **metrics,
        "summary": summary,
        "question_id": str(question.id),
    }
    try:
        return Evaluation.model_validate(payload)
    except ValidationError:
        raise EvaluationReplyError((FAILURE_INVALID_JSON_SHAPE,)) from None
