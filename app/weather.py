"""Client for the Open-Meteo forecast API.

Robustness rules for the external dependency:
- every request has a connect and a read timeout,
- transient failures (connection errors, 502/503/504, 429) are retried twice
  with exponential backoff,
- anything unexpected becomes a WeatherProviderError, which the service layer
  turns into "serve the last cached value" or a clean 503,
- the optional API key is never written to logs or exception messages.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.locations import Location
from app.models import CurrentWeather, DailyForecast, WeatherReport

log = logging.getLogger(__name__)

FORECAST_DAYS = 7

CURRENT_FIELDS = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "weather_code",
)
DAILY_FIELDS = (
    "weather_code",
    "temperature_2m_min",
    "temperature_2m_max",
    "precipitation_sum",
    "precipitation_probability_max",
)


class WeatherProviderError(RuntimeError):
    """The upstream weather service could not deliver a usable answer."""


class WeatherClient(Protocol):
    def fetch(self, location: Location) -> WeatherReport: ...


def _build_session(retries: int) -> requests.Session:
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=0.5,
        status_forcelist=(429, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "weatherwatch (CDS212 student project)"
    return session


class OpenMeteoClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 5.0,
        session: requests.Session | None = None,
        retries: int = 2,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        # (connect timeout, read timeout)
        self._timeout = (min(3.0, timeout_seconds), timeout_seconds)
        self._session = session or _build_session(retries)

    def _params(self, location: Location) -> dict[str, Any]:
        params: dict[str, Any] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "current": ",".join(CURRENT_FIELDS),
            "daily": ",".join(DAILY_FIELDS),
            "timezone": "Europe/Zurich",
            "forecast_days": FORECAST_DAYS,
        }
        if self._api_key:
            params["apikey"] = self._api_key
        return params

    def fetch(self, location: Location) -> WeatherReport:
        try:
            response = self._session.get(
                self._base_url, params=self._params(location), timeout=self._timeout
            )
        except requests.RequestException as exc:
            # Only the exception type: the message of a requests exception can
            # contain the full URL including the apikey query parameter.
            log.warning("upstream request failed for %s: %s", location.slug, type(exc).__name__)
            raise WeatherProviderError(f"upstream unreachable ({type(exc).__name__})") from None

        if response.status_code != 200:
            log.warning("upstream returned HTTP %s for %s", response.status_code, location.slug)
            raise WeatherProviderError(f"upstream returned HTTP {response.status_code}")

        try:
            return parse_report(response.json())
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            log.warning("upstream payload invalid for %s: %s", location.slug, exc)
            raise WeatherProviderError("upstream payload invalid") from None


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"expected a number, got {type(value).__name__}")
    return float(value)


def _code(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"expected a weather code, got {type(value).__name__}")
    return int(value)


def parse_report(payload: Any) -> WeatherReport:
    """Turn the raw Open-Meteo JSON into domain objects, validating the shape."""
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    current = payload["current"]
    daily = payload["daily"]

    report_current = CurrentWeather(
        observed_at=str(current["time"]),
        temperature_c=_num(current.get("temperature_2m")),
        apparent_temperature_c=_num(current.get("apparent_temperature")),
        humidity_pct=_num(current.get("relative_humidity_2m")),
        precipitation_mm=_num(current.get("precipitation")),
        wind_speed_kmh=_num(current.get("wind_speed_10m")),
        weather_code=_code(current.get("weather_code")),
    )

    dates = daily["time"]
    if not isinstance(dates, list):
        raise TypeError("daily.time must be a list")

    def column(name: str) -> list[Any]:
        values = daily.get(name) or [None] * len(dates)
        if len(values) != len(dates):
            raise ValueError(f"daily.{name} has the wrong length")
        return values

    mins, maxs = column("temperature_2m_min"), column("temperature_2m_max")
    rain, prob = column("precipitation_sum"), column("precipitation_probability_max")
    codes = column("weather_code")

    days = [
        DailyForecast(
            date=str(dates[i]),
            temperature_min_c=_num(mins[i]),
            temperature_max_c=_num(maxs[i]),
            precipitation_sum_mm=_num(rain[i]),
            precipitation_probability_pct=_num(prob[i]),
            weather_code=_code(codes[i]),
        )
        for i in range(len(dates))
    ]
    return WeatherReport(current=report_current, daily=days)
