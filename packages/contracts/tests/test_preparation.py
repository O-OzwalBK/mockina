from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from contracts.preparation import (
    MAX_JOB_DESCRIPTION_LENGTH,
    MAX_JOB_TITLE_LENGTH,
    MAX_RESUME_LENGTH,
    Preparation,
    PreparationCreate,
)
from pydantic import ValidationError

LENGTH_LIMITS = {
    "job_title": MAX_JOB_TITLE_LENGTH,
    "job_description": MAX_JOB_DESCRIPTION_LENGTH,
    "resume": MAX_RESUME_LENGTH,
}


def valid_create_data() -> dict[str, Any]:
    """A fresh, valid preparation request as a dictionary, for tests to modify."""
    return {
        "job_title": "Junior React Developer",
        "job_description": "Looking for a junior developer with React experience.",
        "resume": "Built a task tracker with React.",
    }


# PreparationCreate model tests


def test_preparation_create_accepts_valid_values():
    """A request with a title, job description, and resume is valid."""
    request = PreparationCreate.model_validate(valid_create_data())
    assert request.job_title == "Junior React Developer"
    assert request.resume == "Built a task tracker with React."


def test_preparation_create_resume_is_optional():
    """Leaving the resume out, or sending null, both mean there is no resume."""
    data = valid_create_data()
    del data["resume"]
    assert PreparationCreate.model_validate(data).resume is None

    data["resume"] = None
    assert PreparationCreate.model_validate(data).resume is None


@pytest.mark.parametrize("field", ["job_title", "job_description", "resume"])
@pytest.mark.parametrize("blank", ["", "   "])
def test_preparation_create_rejects_blank_text(field, blank):
    """Title, job description, and resume cannot be empty or whitespace-only."""
    data = valid_create_data()
    data[field] = blank
    with pytest.raises(ValidationError):
        PreparationCreate.model_validate(data)


@pytest.mark.parametrize("field", ["job_title", "job_description"])
def test_preparation_create_requires_title_and_description(field):
    """Job title and job description are required; only the resume is optional."""
    data = valid_create_data()
    del data[field]
    with pytest.raises(ValidationError):
        PreparationCreate.model_validate(data)


@pytest.mark.parametrize("field", LENGTH_LIMITS)
def test_preparation_create_accepts_maximum_length(field):
    """Text exactly at the length limit is valid."""
    data = valid_create_data()
    data[field] = "a" * LENGTH_LIMITS[field]
    PreparationCreate.model_validate(data)


@pytest.mark.parametrize("field", LENGTH_LIMITS)
def test_preparation_create_rejects_over_maximum_length(field):
    """Text one character over the length limit is invalid."""
    data = valid_create_data()
    data[field] = "a" * (LENGTH_LIMITS[field] + 1)
    with pytest.raises(ValidationError):
        PreparationCreate.model_validate(data)


def test_preparation_create_strips_surrounding_whitespace():
    """Spaces around a text field are removed rather than stored."""
    data = valid_create_data()
    data["job_title"] = "  Junior React Developer  "
    assert PreparationCreate.model_validate(data).job_title == "Junior React Developer"


@pytest.mark.parametrize("field", ["id", "created_at", "resum"])
def test_preparation_create_rejects_unknown_fields(field):
    """Unknown fields are rejected, so clients cannot set server-owned fields and typos are not ignored."""
    data = valid_create_data()
    data[field] = "x"
    with pytest.raises(ValidationError):
        PreparationCreate.model_validate(data)


# Preparation model tests


def test_preparation_accepts_server_fields():
    """A stored preparation carries the request fields plus an id and a creation time."""
    data = valid_create_data()
    data["id"] = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    data["created_at"] = "2026-10-03T09:30:00Z"
    preparation = Preparation.model_validate(data)
    assert str(preparation.id) == "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    assert preparation.created_at == datetime(2026, 10, 3, 9, 30, tzinfo=UTC)


def test_preparation_generates_unique_ids():
    """Each preparation gets its own id automatically."""
    first = Preparation.model_validate(valid_create_data())
    second = Preparation.model_validate(valid_create_data())
    assert first.id != second.id


def test_preparation_sets_created_at_in_utc():
    """When no creation time is given, it is set to the current time in UTC."""
    preparation = Preparation.model_validate(valid_create_data())
    assert preparation.created_at.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - preparation.created_at) < timedelta(seconds=5)


def test_preparation_rejects_naive_created_at():
    """A creation time without a timezone is invalid."""
    data = valid_create_data()
    data["created_at"] = "2026-10-03T09:30:00"
    with pytest.raises(ValidationError):
        Preparation.model_validate(data)


def test_preparation_converts_created_at_to_utc():
    """A creation time sent with another offset is converted to UTC."""
    data = valid_create_data()
    data["created_at"] = "2026-10-03T15:15:00+05:45"
    preparation = Preparation.model_validate(data)
    assert preparation.created_at.utcoffset() == timedelta(0)
    assert preparation.created_at == datetime(2026, 10, 3, 9, 30, tzinfo=UTC)


def test_preparation_applies_create_rules():
    """A stored preparation follows the same rules as a request, such as no blank title."""
    data = valid_create_data()
    data["job_title"] = "   "
    with pytest.raises(ValidationError):
        Preparation.model_validate(data)


def test_preparation_can_be_built_from_create_data():
    """The server can turn a validated request into a preparation, filling in id and time."""
    request = PreparationCreate.model_validate(valid_create_data())
    preparation = Preparation.model_validate(request.model_dump())
    assert preparation.job_title == request.job_title
    assert preparation.id is not None