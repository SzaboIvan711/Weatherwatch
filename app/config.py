"""Configuration, read exclusively from the environment (twelve-factor, factor III).

The same container image runs locally, in CI, on Render and in Kubernetes; only
the environment differs. Invalid values fail fast at startup with a clear
message instead of surfacing later as confusing runtime errors.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

DEFAULT_WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"


class ConfigError(ValueError):
    """Raised when an environment variable holds an unusable value."""


def _int(env: Mapping[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}, got {value}")
    return value


def _float(
    env: Mapping[str, str], name: str, default: float, minimum: float, maximum: float
) -> float:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}, got {value}")
    return value


def _url(env: Mapping[str, str], name: str, default: str) -> str:
    value = (env.get(name) or "").strip() or default
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(f"{name} must be an absolute http(s) URL")
    return value


def _commit(env: Mapping[str, str]) -> str:
    # The image bakes GIT_COMMIT in at build time and defaults it to "unknown";
    # Render injects RENDER_GIT_COMMIT at runtime. A placeholder must not hide
    # the real value, otherwise CD could not verify which commit is live.
    for name in ("GIT_COMMIT", "RENDER_GIT_COMMIT"):
        value = (env.get(name) or "").strip()
        if value and value != "unknown":
            return value
    return "unknown"


@dataclass(frozen=True)
class Config:
    database_url: str | None
    version: str
    commit: str
    log_level: str
    weather_api_url: str = DEFAULT_WEATHER_API_URL
    # Secret. Never log it, never put it into a URL that is logged.
    weather_api_key: str | None = None
    cache_ttl_seconds: int = 900
    http_timeout_seconds: float = 5.0
    default_city: str = "chur"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        env = os.environ if env is None else env
        log_level = (env.get("LOG_LEVEL") or "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError(f"LOG_LEVEL must be a standard logging level, got {log_level!r}")
        return cls(
            # An empty string is treated like "unset" so that an empty compose
            # variable does not silently produce a broken DSN.
            database_url=(env.get("DATABASE_URL") or "").strip() or None,
            version=(env.get("APP_VERSION") or "").strip() or "0.0.0-dev",
            # GIT_COMMIT is baked in at build time; Render injects
            # RENDER_GIT_COMMIT at runtime. Either lets CD verify which commit
            # is actually live.
            commit=_commit(env),
            log_level=log_level,
            weather_api_url=_url(env, "WEATHER_API_URL", DEFAULT_WEATHER_API_URL),
            weather_api_key=(env.get("WEATHER_API_KEY") or "").strip() or None,
            cache_ttl_seconds=_int(env, "CACHE_TTL_SECONDS", 900, minimum=0, maximum=86_400),
            http_timeout_seconds=_float(
                env, "HTTP_TIMEOUT_SECONDS", 5.0, minimum=0.5, maximum=30.0
            ),
            default_city=(env.get("DEFAULT_CITY") or "chur").strip().lower(),
        )
