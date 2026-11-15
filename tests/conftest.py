from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from prometheus_client import CollectorRegistry

from app import create_app
from app.config import Config
from app.locations import Location
from app.models import CurrentWeather, DailyForecast, WeatherReport
from app.repository import InMemorySnapshotRepository
from app.weather import WeatherProviderError


def make_report(temperature: float = 4.5, days: int = 7) -> WeatherReport:
    return WeatherReport(
        current=CurrentWeather(
            observed_at="2026-11-15T15:00",
            temperature_c=temperature,
            apparent_temperature_c=temperature - 2,
            humidity_pct=80.0,
            precipitation_mm=0.0,
            wind_speed_kmh=12.0,
            weather_code=3,
        ),
        daily=[
            DailyForecast(
                date=f"2026-11-{15 + i}",
                temperature_min_c=-1.0 + i,
                temperature_max_c=6.0 + i,
                precipitation_sum_mm=0.4,
                precipitation_probability_pct=30.0,
                weather_code=61,
            )
            for i in range(days)
        ],
    )


class FakeClient:
    """Stands in for OpenMeteoClient; counts calls and can be told to fail."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail = False
        self.temperature = 4.5

    def fetch(self, location: Location) -> WeatherReport:
        self.calls.append(location.slug)
        if self.fail:
            raise WeatherProviderError("upstream returned HTTP 503")
        return make_report(self.temperature)


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 15, 14, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def config() -> Config:
    return Config(
        database_url=None,
        version="test",
        commit="abc123def4567890",
        log_level="WARNING",
        cache_ttl_seconds=900,
    )


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def repository() -> InMemorySnapshotRepository:
    return InMemorySnapshotRepository()


@pytest.fixture
def app(config, repository, fake_client, clock):
    return create_app(
        config=config,
        repository=repository,
        client=fake_client,
        registry=CollectorRegistry(),
        clock=clock,
    )


@pytest.fixture
def client(app):
    return app.test_client()
