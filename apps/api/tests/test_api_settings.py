"""Tests for ApiSettings: the API's own configuration, separate from the model settings."""

import pytest
from api.settings import ApiSettings
from pydantic import ValidationError

# Every field ApiSettings should have. The parametrized test at the bottom runs over
# this list, so if it is ever empty that test silently passes without checking
# anything. The guard test right after it makes that impossible.
FIELD_NAMES = ("cors_origins", "dev_routes")


@pytest.fixture(autouse=True)
def clear_api_environment(monkeypatch):
    """Remove any exported API_ variable so each test starts from the same place.

    Without this, a value you have exported in your shell would leak into every test
    and the tests would pass or fail depending on the machine.
    """
    for name in ("API_CORS_ORIGINS", "API_DEV_ROUTES"):
        monkeypatch.delenv(name, raising=False)


def build_settings() -> ApiSettings:
    """An ApiSettings built with no .env file read, so only real env vars can influence it.

    `_env_file=None` turns off the .env lookup for this one call. Real environment
    variables are still read, which is exactly what the monkeypatch tests below need.
    """
    return ApiSettings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_field_list_is_not_empty():
    """Guard: FIELD_NAMES must have at least one entry, or the test below checks nothing."""
    assert FIELD_NAMES # pyright: ignore[reportAssertAlwaysTrue]


def test_defaults_are_safe_for_local_development():
    """With nothing set, CORS allows the Vite dev server and the dev routes are off."""
    settings = build_settings()
    assert settings.cors_origins == ("http://localhost:5173",)
    assert settings.dev_routes is False


def test_settings_are_frozen():
    """ApiSettings cannot be changed after it is built."""
    settings = build_settings()
    with pytest.raises(ValidationError):
        settings.dev_routes = True  # type: ignore[misc]


def test_reads_cors_origins_from_environment(monkeypatch):
    """API_CORS_ORIGINS is split on commas into a tuple of origins."""
    monkeypatch.setenv("API_CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
    settings = build_settings()
    assert settings.cors_origins == ("http://localhost:5173", "http://localhost:3000")


def test_whitespace_and_empty_parts_are_dropped(monkeypatch):
    """Extra spaces and empty entries in API_CORS_ORIGINS do not reach the origin list."""
    monkeypatch.setenv("API_CORS_ORIGINS", " http://a ,, http://b ,")
    settings = build_settings()
    assert settings.cors_origins == ("http://a", "http://b")


def test_dev_routes_true_turns_them_on(monkeypatch):
    """API_DEV_ROUTES=true means the developer routes will be registered."""
    monkeypatch.setenv("API_DEV_ROUTES", "true")
    settings = build_settings()
    assert settings.dev_routes is True


def test_dev_routes_false_keeps_them_off(monkeypatch):
    """API_DEV_ROUTES=false means the developer routes will not be registered."""
    monkeypatch.setenv("API_DEV_ROUTES", "false")
    settings = build_settings()
    assert settings.dev_routes is False


def test_bad_dev_routes_value_raises(monkeypatch):
    """A value that is not a boolean raises ValidationError naming the field."""
    monkeypatch.setenv("API_DEV_ROUTES", "maybe")
    with pytest.raises(ValidationError) as info:
        build_settings()
    assert "dev_routes" in str(info.value)


@pytest.mark.parametrize("field_name", FIELD_NAMES)
def test_every_field_has_a_description(field_name):
    """Every field carries a description, so printed settings explain themselves."""
    field = ApiSettings.model_fields[field_name]
    assert field.description
