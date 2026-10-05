from datetime import UTC, datetime, timedelta

import pytest
from contracts.common import ImmutableModel, UtcDatetime, utc_now
from pydantic import BaseModel, ValidationError


class Stamp(BaseModel):
    """A model with one UTC datetime field, used to test UtcDatetime."""

    at: UtcDatetime


class Label(ImmutableModel):
    """A tiny immutable model, used to test the shared behaviour."""

    name: str
    size: int = 1


# utc_now and UtcDatetime


def test_utc_now_is_timezone_aware_utc():
    """utc_now returns the current time with a UTC offset."""
    now = utc_now()
    assert now.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - now) < timedelta(seconds=5)


def test_utc_datetime_accepts_utc_values():
    """A time already in UTC is kept as it is."""
    stamp = Stamp.model_validate({"at": "2026-10-04T09:00:00Z"})
    assert stamp.at == datetime(2026, 10, 4, 9, 0, tzinfo=UTC)


def test_utc_datetime_converts_other_offsets():
    """A time with another offset is converted to UTC."""
    stamp = Stamp.model_validate({"at": "2026-10-04T14:45:00+05:45"})
    assert stamp.at.utcoffset() == timedelta(0)
    assert stamp.at == datetime(2026, 10, 4, 9, 0, tzinfo=UTC)


def test_utc_datetime_rejects_naive_values():
    """A time without a timezone is invalid."""
    with pytest.raises(ValidationError):
        Stamp.model_validate({"at": "2026-10-04T09:00:00"})


# ImmutableModel tests


def test_immutable_model_cannot_be_assigned_to():
    """Fields cannot be changed after creation."""
    label = Label.model_validate({"name": "a"})
    with pytest.raises(ValidationError):
        label.name = "b"


def test_immutable_model_rejects_unknown_fields():
    """Unknown fields are rejected so typos are not silently ignored."""
    with pytest.raises(ValidationError):
        Label.model_validate({"name": "a", "colour": "red"})


def test_immutable_model_strips_whitespace():
    """Spaces around text fields are removed rather than stored."""
    assert Label.model_validate({"name": "  a  "}).name == "a"


def test_updated_returns_a_new_copy():
    """updated() returns a changed copy and leaves the original untouched."""
    original = Label.model_validate({"name": "a"})
    changed = original.updated(size=5)
    assert changed.size == 5
    assert original.size == 1


def test_updated_rejects_invalid_values():
    """updated() validates its changes, so a wrong type is rejected."""
    with pytest.raises(ValidationError):
        Label.model_validate({"name": "a"}).updated(size="large")


def test_updated_rejects_unknown_fields():
    """A typo in an updated() argument raises an error instead of doing nothing."""
    with pytest.raises(ValidationError):
        Label.model_validate({"name": "a"}).updated(sise=5)
