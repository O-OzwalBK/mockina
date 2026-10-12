import pytest
from llm_gateway import LLMSettings
from pydantic import ValidationError

SETTING_VARIABLES = [
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_API_KEY",
    "LLM_CONTEXT_TOKENS",
    "LLM_MAX_OUTPUT_TOKENS",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
]


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    """Run every test with no LLM_ variables set and from an empty folder, so a real .env cannot leak in."""
    for name in SETTING_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def required(monkeypatch):
    """Set the two variables that have no default."""
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "llama3.1:8b")


def load() -> LLMSettings:
    """Read the settings from the environment only, ignoring any .env file."""
    return LLMSettings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_required_values_are_read_from_the_environment(required):
    """The base URL and model name come from LLM_BASE_URL and LLM_MODEL."""
    settings = load()
    assert settings.base_url == "http://localhost:11434/v1"
    assert settings.model == "llama3.1:8b"


def test_optional_values_have_safe_defaults(required):
    """Without any optional variables, the defaults are used and there is no API key."""
    settings = load()
    assert settings.api_key is None
    assert settings.context_tokens == 8192
    assert settings.max_output_tokens == 1024
    assert settings.timeout_seconds == 60.0
    assert settings.max_retries == 2


def test_optional_values_can_be_overridden(required, monkeypatch):
    """Each optional variable replaces its default."""
    monkeypatch.setenv("LLM_API_KEY", "secret-key")
    monkeypatch.setenv("LLM_CONTEXT_TOKENS", "32768")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "2048")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "15.5")
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    settings = load()
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "secret-key"
    assert settings.context_tokens == 32768
    assert settings.max_output_tokens == 2048
    assert settings.timeout_seconds == 15.5
    assert settings.max_retries == 0


@pytest.mark.parametrize("missing", ["LLM_BASE_URL", "LLM_MODEL"])
def test_base_url_and_model_are_required(required, monkeypatch, missing):
    """Starting without a base URL or a model name fails immediately instead of at the first request."""
    monkeypatch.delenv(missing)
    with pytest.raises(ValidationError):
        load()


def test_trailing_slash_and_spaces_are_removed_from_the_base_url(monkeypatch):
    """A base URL written with a trailing slash or stray spaces is cleaned, so joining paths never doubles a slash."""
    monkeypatch.setenv("LLM_BASE_URL", "  https://api.example.com/v1/  ")
    monkeypatch.setenv("LLM_MODEL", "m")
    assert load().base_url == "https://api.example.com/v1"


@pytest.mark.parametrize(
    "bad_url",
    ["localhost:11434/v1", "ftp://example.com/v1", "https://", "api.example.com/v1"],
)
def test_base_url_must_be_a_full_http_or_https_address(monkeypatch, bad_url):
    """An address without http:// or https:// and a host is rejected."""
    monkeypatch.setenv("LLM_BASE_URL", bad_url)
    monkeypatch.setenv("LLM_MODEL", "m")
    with pytest.raises(ValidationError, match="http"):
        load()


def test_api_key_is_hidden_when_settings_are_printed(required, monkeypatch):
    """The API key never appears in the text form of the settings, so it cannot leak into logs."""
    monkeypatch.setenv("LLM_API_KEY", "super-secret-value")
    settings = load()
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings)


def test_an_empty_api_key_means_no_key(required, monkeypatch):
    """LLM_API_KEY left empty, as in .env.example, behaves like not setting it, for local servers."""
    monkeypatch.setenv("LLM_API_KEY", "")
    assert load().api_key is None


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("LLM_CONTEXT_TOKENS", "100"),
        ("LLM_MAX_OUTPUT_TOKENS", "0"),
        ("LLM_TIMEOUT_SECONDS", "0"),
        ("LLM_MAX_RETRIES", "-1"),
        ("LLM_MAX_RETRIES", "6"),
    ],
)
def test_numbers_outside_their_limits_are_rejected(required, monkeypatch, variable, value):
    """Context size, output length, timeout, and retries must each stay within sensible limits."""
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValidationError):
        load()


def test_the_reply_limit_must_leave_room_for_a_prompt(required, monkeypatch):
    """A longest reply as big as the whole context window is rejected, because no prompt would fit."""
    monkeypatch.setenv("LLM_CONTEXT_TOKENS", "4096")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "4096")
    with pytest.raises(ValidationError, match="max_output_tokens"):
        load()


def test_settings_cannot_be_changed_after_loading(required):
    """Settings are frozen once loaded, so no part of the program can change them by accident."""
    settings = load()
    with pytest.raises(ValidationError):
        setattr(settings, "model", "another-model")


def write_env_file(folder, text):
    """Create a .env file in the given folder and return the folder."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ".env").write_text(text, encoding="utf-8")
    return folder


def test_env_file_in_the_current_folder_is_read(monkeypatch, tmp_path):
    """Settings are loaded from a .env file in the folder the program starts from."""
    monkeypatch.chdir(write_env_file(tmp_path / "repo", "LLM_BASE_URL=http://a/v1\nLLM_MODEL=m1\n"))
    settings = LLMSettings()  # pyright: ignore[reportCallIssue]
    assert settings.base_url == "http://a/v1"
    assert settings.model == "m1"


def test_env_file_two_folders_up_is_found_from_apps_api(monkeypatch, tmp_path):
    """Starting the API from apps/api still finds the .env in the repo root."""
    repo = write_env_file(tmp_path / "repo", "LLM_BASE_URL=http://root/v1\nLLM_MODEL=root-model\n")
    api_folder = repo / "apps" / "api"
    api_folder.mkdir(parents=True)
    monkeypatch.chdir(api_folder)
    assert LLMSettings().model == "root-model"  # pyright: ignore[reportCallIssue]


def test_env_file_in_the_current_folder_beats_the_one_at_the_root(monkeypatch, tmp_path):
    """When both exist, the .env in the folder you start from wins over the repo root's."""
    repo = write_env_file(tmp_path / "repo", "LLM_BASE_URL=http://root/v1\nLLM_MODEL=root-model\n")
    api_folder = write_env_file(repo / "apps" / "api", "LLM_MODEL=local-model\n")
    monkeypatch.chdir(api_folder)
    settings = LLMSettings()  # pyright: ignore[reportCallIssue]
    assert settings.model == "local-model"
    assert settings.base_url == "http://root/v1"


def test_real_environment_variables_beat_the_env_file(monkeypatch, tmp_path):
    """A variable set in the real environment wins over the same one in .env."""
    monkeypatch.chdir(
        write_env_file(tmp_path / "repo", "LLM_BASE_URL=http://a/v1\nLLM_MODEL=file\n")
    )
    monkeypatch.setenv("LLM_MODEL", "from-environment")
    assert LLMSettings().model == "from-environment"  # pyright: ignore[reportCallIssue]


def test_unrelated_lines_in_the_env_file_are_ignored(monkeypatch, tmp_path):
    """Other settings in the same .env file, such as ones for other tools, do not cause an error."""
    text = "LLM_BASE_URL=http://a/v1\nLLM_MODEL=m\nDATABASE_URL=sqlite:///x.db\nLLM_API_KEY=\n"
    monkeypatch.chdir(write_env_file(tmp_path / "repo", text))
    settings = LLMSettings()  # pyright: ignore[reportCallIssue]
    assert settings.model == "m"
    assert settings.api_key is None
