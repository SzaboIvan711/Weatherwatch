import logging

import pytest
import requests

from app.locations import LOCATIONS, UnknownLocationError, resolve
from app.models import WeatherReport, describe
from app.weather import FORECAST_DAYS, OpenMeteoClient, WeatherProviderError, parse_report

PAYLOAD = {
    "current": {
        "time": "2026-11-15T15:00",
        "temperature_2m": 3.9,
        "apparent_temperature": 0.4,
        "relative_humidity_2m": 76,
        "precipitation": 0.0,
        "wind_speed_10m": 8.3,
        "weather_code": 2,
    },
    "daily": {
        "time": ["2026-11-15", "2026-11-16"],
        "weather_code": [2, 71],
        "temperature_2m_min": [-2.1, -4.0],
        "temperature_2m_max": [5.3, 1.2],
        "precipitation_sum": [0.0, 3.4],
        "precipitation_probability_max": [10, 80],
    },
}


class FakeResponse:
    def __init__(self, status_code=200, payload=None, json_error=False):
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.requests = []

    def get(self, url, params=None, timeout=None):
        self.requests.append({"url": url, "params": params, "timeout": timeout})
        if self.exc:
            raise self.exc
        return self.response


def client_with(session, api_key=None):
    return OpenMeteoClient(
        "https://api.open-meteo.com/v1/forecast", api_key=api_key, session=session
    )


def test_parse_report_maps_fields():
    report = parse_report(PAYLOAD)
    assert report.current.temperature_c == 3.9
    assert report.current.humidity_pct == 76.0
    assert report.current.description == "Teilweise bewölkt"
    assert [d.date for d in report.daily] == ["2026-11-15", "2026-11-16"]
    assert report.daily[1].description == "Leichter Schneefall"
    assert report.daily[1].precipitation_probability_pct == 80.0


def test_report_round_trips_through_dict():
    report = parse_report(PAYLOAD)
    assert WeatherReport.from_dict(report.to_dict()) == report


def test_missing_optional_values_become_none():
    payload = {
        "current": {"time": "2026-11-15T15:00"},
        "daily": {"time": ["2026-11-15"]},
    }
    report = parse_report(payload)
    assert report.current.temperature_c is None
    assert report.current.description == "Unbekannt"
    assert report.daily[0].temperature_max_c is None


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"current": {}},
        {"current": {"time": "x"}, "daily": {"time": "not-a-list"}},
        {"current": {"time": "x", "temperature_2m": "warm"}, "daily": {"time": []}},
        {"current": {"time": "x", "weather_code": True}, "daily": {"time": []}},
        {"current": {"time": "x"}, "daily": {"time": ["a", "b"], "weather_code": [1]}},
    ],
)
def test_malformed_payload_is_rejected(payload):
    with pytest.raises((TypeError, KeyError, ValueError)):
        parse_report(payload)


def test_unknown_weather_code_is_described_as_unknown():
    assert describe(1234) == "Unbekannt"


def test_client_sends_expected_query():
    session = FakeSession(FakeResponse(payload=PAYLOAD))
    client_with(session).fetch(LOCATIONS["chur"])
    params = session.requests[0]["params"]
    assert params["latitude"] == LOCATIONS["chur"].latitude
    assert params["forecast_days"] == FORECAST_DAYS
    assert params["timezone"] == "Europe/Zurich"
    assert "apikey" not in params
    assert session.requests[0]["timeout"] == (3.0, 5.0)


def test_client_adds_api_key_only_when_configured():
    session = FakeSession(FakeResponse(payload=PAYLOAD))
    client_with(session, api_key="top-secret").fetch(LOCATIONS["chur"])
    assert session.requests[0]["params"]["apikey"] == "top-secret"


def test_client_maps_http_error(caplog):
    session = FakeSession(FakeResponse(status_code=503))
    with pytest.raises(WeatherProviderError, match="HTTP 503"):
        client_with(session).fetch(LOCATIONS["chur"])


def test_client_maps_network_error_without_leaking_the_key(caplog):
    leaky = requests.ConnectionError("failed for https://x/?apikey=top-secret")
    session = FakeSession(exc=leaky)
    with caplog.at_level(logging.DEBUG), pytest.raises(WeatherProviderError) as info:
        client_with(session, api_key="top-secret").fetch(LOCATIONS["chur"])
    assert "top-secret" not in str(info.value)
    assert info.value.__cause__ is None
    assert "top-secret" not in caplog.text


def test_client_maps_invalid_json():
    session = FakeSession(FakeResponse(json_error=True))
    with pytest.raises(WeatherProviderError, match="invalid"):
        client_with(session).fetch(LOCATIONS["chur"])


def test_client_builds_retrying_session_by_default():
    client = OpenMeteoClient("https://api.open-meteo.com/v1/forecast")
    adapter = client._session.get_adapter("https://api.open-meteo.com")
    assert adapter.max_retries.total == 1
    assert 503 in adapter.max_retries.status_forcelist


def test_resolve_location():
    assert resolve(None, "chur").name == "Chur"
    assert resolve(" Davos ", "chur").slug == "davos"
    with pytest.raises(UnknownLocationError):
        resolve("atlantis", "chur")
