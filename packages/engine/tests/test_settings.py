import pytest
from engine import EngineSettings
from pydantic import ValidationError

ENGINE_VARIABLES = [
    "ENGINE_DEFAULT_QUESTION_COUNT",
    "ENGINE_DEFAULT_ANSWER_TIME_SECONDS",
    "ENGINE_DEFAULT_MODEL_DECIDES_MIN",
    "ENGINE_DEFAULT_MODEL_DECIDES_MAX",
]

OVERRIDE_CASES = [
    ("ENGINE_DEFAULT_QUESTION_COUNT", "7", "default_question_count"),
    ("ENGINE_DEFAULT_ANSWER_TIME_SECONDS", "600", "default_answer_time_seconds"),
    ("ENGINE_DEFAULT_MODEL_DECIDES_MIN", "4", "default_model_decides_min"),
    ("ENGINE_DEFAULT_MODEL_DECIDES_MAX", "15", "default_model_decides_max"),
]

OUT_OF_RANGE_CASES = [
    ("ENGINE_DEFAULT_QUESTION_COUNT", "0"),
    ("ENGINE_DEFAULT_QUESTION_COUNT", "101"),
    ("ENGINE_DEFAULT_ANSWER_TIME_SECONDS", "59"),
    ("ENGINE_DEFAULT_ANSWER_TIME_SECONDS", "3601"),
    ("ENGINE_DEFAULT_MODEL_DECIDES_MIN", "0"),
    ("ENGINE_DEFAULT_MODEL_DECIDES_MIN", "11"),
    ("ENGINE_DEFAULT_MODEL_DECIDES_MAX", "1"),
    ("ENGINE_DEFAULT_MODEL_DECIDES_MAX", "21"),
]


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    """Run every test with no ENGINE_ variables set, so a real .env cannot leak in."""
    for name in ENGINE_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def load() -> EngineSettings:
    """Read the settings from the environment only, ignoring any .env file."""
    return EngineSettings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_defaults_are_the_engine_policy():
    """The four instance defaults are the agreed 5 questions, 900 seconds, 3 to 12 questions."""
    settings = load()
    assert settings.default_question_count == 5
    assert settings.default_answer_time_seconds == 900
    assert settings.default_model_decides_min == 3
    assert settings.default_model_decides_max == 12


@pytest.mark.parametrize(("variable", "value", "attribute"), OVERRIDE_CASES)
def test_each_setting_reads_its_own_environment_variable(monkeypatch, variable, value, attribute):
    """Each ENGINE_DEFAULT_* variable replaces its default."""
    monkeypatch.setenv(variable, value)
    assert getattr(load(), attribute) == int(value)


@pytest.mark.parametrize(("variable", "value"), OUT_OF_RANGE_CASES)
def test_values_outside_the_contract_bounds_are_rejected(monkeypatch, variable, value):
    """A default outside the contract's hard limits stops startup instead of being clamped."""
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValidationError):
        load()


def test_model_decides_min_must_be_below_max(monkeypatch):
    """Defaults that leave the model no range to decide in are rejected at startup."""
    monkeypatch.setenv("ENGINE_DEFAULT_MODEL_DECIDES_MIN", "10")
    monkeypatch.setenv("ENGINE_DEFAULT_MODEL_DECIDES_MAX", "5")
    with pytest.raises(ValidationError, match="default_model_decides_min"):
        load()


def test_settings_are_frozen():
    """Settings cannot be changed after loading, so no part of the engine can alter them."""
    settings = load()
    with pytest.raises(ValidationError):
        settings.default_question_count = 10


def test_only_engine_prefixed_variables_are_read(monkeypatch):
    """A variable without the ENGINE_ prefix is ignored, so other settings cannot collide."""
    monkeypatch.setenv("DEFAULT_QUESTION_COUNT", "9")
    assert load().default_question_count == 5


def test_unknown_engine_variables_are_ignored(monkeypatch):
    """An unrelated ENGINE_ variable does not stop startup."""
    monkeypatch.setenv("ENGINE_SOMETHING_UNKNOWN", "value")
    assert load().default_question_count == 5
