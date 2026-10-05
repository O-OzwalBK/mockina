from datetime import UTC, datetime
from typing import Annotated, Any, Self

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict


def utc_now() -> datetime:
    """The current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def _to_utc(value: datetime) -> datetime:
    """Convert a timezone-aware datetime to UTC."""
    return value.astimezone(UTC)


# A timezone-aware datetime that is always stored in UTC, whatever offset was sent.
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]


class ImmutableModel(BaseModel):
    """Base class for models that never change after they are created.

    Instances cannot be modified, unknown fields are rejected, and surrounding
    whitespace is stripped from text. To get a changed version, call `updated()`,
    which re-validates the result. Do not use `model_copy(update=...)`, because
    it skips validation and can produce an invalid model.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    def updated(self, **changes: Any) -> Self:
        """Return a new, validated copy with the given fields changed.

        Changes that break the model's rules raise a ValidationError instead of
        being stored.
        """
        return type(self).model_validate({**self.model_dump(), **changes})
