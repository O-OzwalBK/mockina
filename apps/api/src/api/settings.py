from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class ApiSettings(BaseSettings):
    """Configuration for API behavior that is separate from the model settings."""

    model_config = SettingsConfigDict(
        env_prefix="API_",
        env_file=("../../.env", ".env"),
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        str_strip_whitespace=True,
    )

    cors_origins: Annotated[tuple[str, ...], NoDecode] = Field(
        default=("http://localhost:5173",),
        description="Comma-separated browser origins allowed to call the API.",
        examples=[("http://localhost:5173",)],
        min_length=1,
    )
    dev_routes: bool = Field(
        default=False,
        description=(
            "Whether developer-only model routes are registered. Keep disabled in deployed "
            "copies of the API."
        ),
        examples=[False],
    )

    anon_retention_days: int = Field(
        default=30,
        ge=0,
        description=(
            "How many days an anonymous user may stay inactive before their data is due for "
            "deletion; 0 means the data is kept until the user deletes it. Shown to the browser "
            "through GET /v1/capabilities. The scheduled purge that enforces it is not built "
            "yet, so today the value is only advertised."
        ),
        examples=[30],
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Turn the comma-separated environment value into a clean tuple of origins."""
        if isinstance(value, str):
            return tuple(origin.strip() for origin in value.split(",") if origin.strip())
        return value
