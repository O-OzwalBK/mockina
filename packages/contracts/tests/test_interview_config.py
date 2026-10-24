import json
from pathlib import Path
from typing import Any

import pytest
from contracts.interview_config import (
    MAX_ANSWER_TIME_SECONDS,
    MAX_MODEL_DECIDES_MAX_QUESTIONS,
    MAX_MODEL_DECIDES_MIN_QUESTIONS,
    MAX_QUESTION_COUNT,
    MIN_ANSWER_TIME_SECONDS,
    MIN_MODEL_DECIDES_MAX_QUESTIONS,
    MIN_MODEL_DECIDES_MIN_QUESTIONS,
    MIN_QUESTION_COUNT,
    AnswerTimeConfig,
    InterviewConfig,
    ModelDecidesConfig,
    QuestionCountConfig,
)
from pydantic import TypeAdapter, ValidationError

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "docs" / "schemas"
INTERVIEW_CONFIG = TypeAdapter(InterviewConfig)
MODEL_NAMES = ("AnswerTimeConfig", "ModelDecidesConfig", "QuestionCountConfig")


def valid_question_count_data() -> dict[str, Any]:
    """A fresh, valid question-count rule as a dictionary."""
    return {"rule": "question_count", "count": 5}


def valid_answer_time_data() -> dict[str, Any]:
    """A fresh, valid answer-time rule as a dictionary."""
    return {"rule": "answer_time", "max_seconds": 900}


def valid_model_decides_data() -> dict[str, Any]:
    """A fresh, valid model-decides rule as a dictionary."""
    return {"rule": "model_decides", "min_questions": 3, "max_questions": 12}


# Each rule's class, its valid data factory, and the fields it accepts.
RULES = [
    (QuestionCountConfig, valid_question_count_data),
    (AnswerTimeConfig, valid_answer_time_data),
    (ModelDecidesConfig, valid_model_decides_data),
]
RULE_IDS = [rule_class.__name__ for rule_class, _ in RULES]


def test_every_rule_has_a_case():
    """All three end rules appear in the parametrized cases, so none is silently skipped."""
    assert {rule_class for rule_class, _ in RULES} == {
        AnswerTimeConfig,
        ModelDecidesConfig,
        QuestionCountConfig,
    }


@pytest.mark.parametrize(("rule_class", "data_factory"), RULES, ids=RULE_IDS)
def test_each_rule_accepts_valid_values(rule_class, data_factory):
    """A rule accepts values inside its limits and keeps its discriminator name."""
    data = data_factory()
    config = rule_class.model_validate(data)
    assert isinstance(config, rule_class)
    assert config.rule == data["rule"]


BOUNDARY_CASES = [
    (QuestionCountConfig, "count", MIN_QUESTION_COUNT),
    (QuestionCountConfig, "count", MAX_QUESTION_COUNT),
    (AnswerTimeConfig, "max_seconds", MIN_ANSWER_TIME_SECONDS),
    (AnswerTimeConfig, "max_seconds", MAX_ANSWER_TIME_SECONDS),
    (ModelDecidesConfig, "min_questions", MIN_MODEL_DECIDES_MIN_QUESTIONS),
    (ModelDecidesConfig, "min_questions", MAX_MODEL_DECIDES_MIN_QUESTIONS),
    (ModelDecidesConfig, "max_questions", MIN_MODEL_DECIDES_MAX_QUESTIONS),
    (ModelDecidesConfig, "max_questions", MAX_MODEL_DECIDES_MAX_QUESTIONS),
]
BOUNDARY_IDS = [
    f"{rule_class.__name__}.{field}={value}" for rule_class, field, value in BOUNDARY_CASES
]

OUT_OF_RANGE_CASES = [
    (QuestionCountConfig, "count", MIN_QUESTION_COUNT - 1),
    (QuestionCountConfig, "count", MAX_QUESTION_COUNT + 1),
    (AnswerTimeConfig, "max_seconds", MIN_ANSWER_TIME_SECONDS - 1),
    (AnswerTimeConfig, "max_seconds", MAX_ANSWER_TIME_SECONDS + 1),
    (ModelDecidesConfig, "min_questions", MIN_MODEL_DECIDES_MIN_QUESTIONS - 1),
    (ModelDecidesConfig, "min_questions", MAX_MODEL_DECIDES_MIN_QUESTIONS + 1),
    (ModelDecidesConfig, "max_questions", MIN_MODEL_DECIDES_MAX_QUESTIONS - 1),
    (ModelDecidesConfig, "max_questions", MAX_MODEL_DECIDES_MAX_QUESTIONS + 1),
]
OUT_OF_RANGE_IDS = [
    f"{rule_class.__name__}.{field}={value}" for rule_class, field, value in OUT_OF_RANGE_CASES
]


def _data_for(rule_class: type) -> dict[str, Any]:
    """The valid data factory for one rule class."""
    for candidate, data_factory in RULES:
        if candidate is rule_class:
            return data_factory()
    raise AssertionError(f"No valid data factory for {rule_class.__name__}")


def _data_with(rule_class: type, field: str, value: int) -> dict[str, Any]:
    """Valid data with one field set, keeping the model-decides pair in range when possible."""
    data = _data_for(rule_class)
    data[field] = value
    if rule_class is ModelDecidesConfig:
        if field == "min_questions" and value >= data["max_questions"]:
            data["max_questions"] = MAX_MODEL_DECIDES_MAX_QUESTIONS
        elif field == "max_questions" and value <= data["min_questions"]:
            data["min_questions"] = MIN_MODEL_DECIDES_MIN_QUESTIONS
    return data


@pytest.mark.parametrize(("rule_class", "field", "value"), BOUNDARY_CASES, ids=BOUNDARY_IDS)
def test_each_rule_accepts_its_boundaries(rule_class, field, value):
    """A value exactly at the lower or upper limit is valid."""
    data = _data_with(rule_class, field, value)
    assert getattr(rule_class.model_validate(data), field) == value


@pytest.mark.parametrize(("rule_class", "field", "value"), OUT_OF_RANGE_CASES, ids=OUT_OF_RANGE_IDS)
def test_each_rule_rejects_values_outside_its_limits(rule_class, field, value):
    """A value below the lower limit or above the upper limit is rejected."""
    data = _data_with(rule_class, field, value)
    with pytest.raises(ValidationError):
        rule_class.model_validate(data)


@pytest.mark.parametrize(("min_questions", "max_questions"), [(5, 5), (6, 5)])
def test_model_decides_requires_min_strictly_below_max(min_questions, max_questions):
    """Equal or inverted limits leave the model no decision to make, so they are rejected."""
    data = valid_model_decides_data()
    data["min_questions"] = min_questions
    data["max_questions"] = max_questions
    with pytest.raises(ValidationError):
        ModelDecidesConfig.model_validate(data)


@pytest.mark.parametrize(("rule_class", "data_factory"), RULES, ids=RULE_IDS)
def test_union_parses_each_rule_by_its_name(rule_class, data_factory):
    """The discriminated union selects the class named by the rule field."""
    parsed = INTERVIEW_CONFIG.validate_python(data_factory())
    assert type(parsed) is rule_class


def test_union_rejects_an_unknown_rule():
    """A rule name that is not one of the three is rejected."""
    with pytest.raises(ValidationError):
        INTERVIEW_CONFIG.validate_python({"rule": "time_limit", "count": 5})


def test_union_requires_the_rule_field():
    """Without the discriminator the union cannot choose a rule, so validation raises."""
    with pytest.raises(ValidationError):
        INTERVIEW_CONFIG.validate_python({"count": 5})


def test_union_rejects_fields_belonging_to_another_rule():
    """One rule's fields cannot ride along with another rule, because unknown fields are rejected."""
    with pytest.raises(ValidationError):
        INTERVIEW_CONFIG.validate_python({"rule": "question_count", "count": 5, "max_seconds": 900})


@pytest.mark.parametrize("model_name", MODEL_NAMES)
def test_generated_schema_documents_every_property(model_name):
    """Each rule has a generated schema file, and every property in it has a description."""
    path = SCHEMA_DIR / f"{model_name}.json"
    assert path.is_file(), f"{path} was not generated; run scripts/export_schemas.py"
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert "rule" in schema["properties"]
    for property_name, details in schema["properties"].items():
        assert details.get("description"), f"{model_name}.{property_name} has no description"
