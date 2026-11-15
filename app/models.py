"""Domain objects. Plain dataclasses that serialise to JSON and back.

The same dict shape is used for the API responses and for the JSONB payload
in Postgres, so a snapshot written today can be read back unchanged later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

# WMO weather interpretation codes, as used by Open-Meteo.
# https://open-meteo.com/en/docs (section "WMO Weather interpretation codes")
WEATHER_CODES: dict[int, str] = {
    0: "Klar",
    1: "Überwiegend klar",
    2: "Teilweise bewölkt",
    3: "Bedeckt",
    45: "Nebel",
    48: "Nebel mit Reifansatz",
    51: "Leichter Nieselregen",
    53: "Nieselregen",
    55: "Starker Nieselregen",
    56: "Leichter gefrierender Nieselregen",
    57: "Gefrierender Nieselregen",
    61: "Leichter Regen",
    63: "Regen",
    65: "Starker Regen",
    66: "Leichter gefrierender Regen",
    67: "Gefrierender Regen",
    71: "Leichter Schneefall",
    73: "Schneefall",
    75: "Starker Schneefall",
    77: "Schneegriesel",
    80: "Leichte Regenschauer",
    81: "Regenschauer",
    82: "Heftige Regenschauer",
    85: "Leichte Schneeschauer",
    86: "Schneeschauer",
    95: "Gewitter",
    96: "Gewitter mit leichtem Hagel",
    99: "Gewitter mit Hagel",
}


def describe(code: int | None) -> str:
    if code is None:
        return "Unbekannt"
    return WEATHER_CODES.get(code, "Unbekannt")


@dataclass(frozen=True)
class CurrentWeather:
    observed_at: str
    temperature_c: float | None
    apparent_temperature_c: float | None
    humidity_pct: float | None
    precipitation_mm: float | None
    wind_speed_kmh: float | None
    weather_code: int | None

    @property
    def description(self) -> str:
        return describe(self.weather_code)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "description": self.description}


@dataclass(frozen=True)
class DailyForecast:
    date: str
    temperature_min_c: float | None
    temperature_max_c: float | None
    precipitation_sum_mm: float | None
    precipitation_probability_pct: float | None
    weather_code: int | None

    @property
    def description(self) -> str:
        return describe(self.weather_code)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "description": self.description}


@dataclass(frozen=True)
class WeatherReport:
    current: CurrentWeather
    daily: list[DailyForecast] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current": asdict(self.current),
            "daily": [asdict(day) for day in self.daily],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WeatherReport:
        return cls(
            current=CurrentWeather(**data["current"]),
            daily=[DailyForecast(**day) for day in data.get("daily", [])],
        )


@dataclass(frozen=True)
class Snapshot:
    """One successful upstream fetch for one city. Doubles as cache entry."""

    city: str
    fetched_at: datetime  # timezone-aware, UTC
    report: WeatherReport
    id: int | None = None

    def age_seconds(self, now: datetime) -> float:
        return (now - self.fetched_at).total_seconds()
