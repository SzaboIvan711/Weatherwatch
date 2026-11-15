import pytest

from app.config import DEFAULT_WEATHER_API_URL, Config, ConfigError


def test_defaults_when_environment_is_empty():
    config = Config.from_env({})
    assert config.database_url is None
    assert config.version == "0.0.0-dev"
    assert config.commit == "unknown"
    assert config.log_level == "INFO"
    assert config.weather_api_url == DEFAULT_WEATHER_API_URL
    assert config.weather_api_key is None
    assert config.cache_ttl_seconds == 900
    assert config.http_timeout_seconds == 5.0
    assert config.default_city == "chur"


def test_values_are_read_from_environment():
    config = Config.from_env(
        {
            "DATABASE_URL": "postgresql://u:p@db:5432/x",
            "APP_VERSION": "1.2.3",
            "GIT_COMMIT": "deadbeef",
            "LOG_LEVEL": "debug",
            "WEATHER_API_URL": "https://customer-api.open-meteo.com/v1/forecast",
            "WEATHER_API_KEY": "  key  ",
            "CACHE_TTL_SECONDS": "60",
            "HTTP_TIMEOUT_SECONDS": "2.5",
            "DEFAULT_CITY": "Bern",
        }
    )
    assert config.database_url == "postgresql://u:p@db:5432/x"
    assert config.version == "1.2.3"
    assert config.commit == "deadbeef"
    assert config.log_level == "DEBUG"
    assert config.weather_api_key == "key"
    assert config.cache_ttl_seconds == 60
    assert config.http_timeout_seconds == 2.5
    assert config.default_city == "bern"


def test_empty_database_url_means_in_memory():
    assert Config.from_env({"DATABASE_URL": ""}).database_url is None


def test_render_commit_is_used_as_fallback():
    assert Config.from_env({"RENDER_GIT_COMMIT": "cafe42"}).commit == "cafe42"


def test_placeholder_build_commit_does_not_hide_render_commit():
    env = {"GIT_COMMIT": "unknown", "RENDER_GIT_COMMIT": "cafe42"}
    assert Config.from_env(env).commit == "cafe42"


@pytest.mark.parametrize(
    "env",
    [
        {"CACHE_TTL_SECONDS": "abc"},
        {"CACHE_TTL_SECONDS": "-1"},
        {"HTTP_TIMEOUT_SECONDS": "fast"},
        {"HTTP_TIMEOUT_SECONDS": "99"},
        {"WEATHER_API_URL": "ftp://example.com"},
        {"WEATHER_API_URL": "not a url"},
        {"LOG_LEVEL": "LOUD"},
    ],
)
def test_invalid_values_fail_fast(env):
    with pytest.raises(ConfigError):
        Config.from_env(env)
