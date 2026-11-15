import pytest

from app.repository import RepositoryError


def test_locations_lists_allow_list_with_default(client):
    data = client.get("/api/locations").get_json()
    assert data["default"] == "chur"
    slugs = [loc["slug"] for loc in data["locations"]]
    assert "chur" in slugs and "zuerich" in slugs


def test_weather_defaults_to_chur(client, fake_client):
    response = client.get("/api/weather")
    assert response.status_code == 200
    data = response.get_json()
    assert data["location"]["slug"] == "chur"
    assert data["current"]["temperature_c"] == 4.5
    assert data["current"]["description"] == "Bedeckt"
    assert data["source"] == "upstream"
    assert data["stale"] is False
    assert "Open-Meteo" in data["attribution"]
    assert fake_client.calls == ["chur"]


def test_weather_for_other_city_is_case_insensitive(client, fake_client):
    data = client.get("/api/weather?city=ZUERICH").get_json()
    assert data["location"]["name"] == "Zürich"
    assert fake_client.calls == ["zuerich"]


def test_unknown_city_returns_404_with_known_cities(client, fake_client):
    response = client.get("/api/weather?city=atlantis")
    assert response.status_code == 404
    data = response.get_json()
    assert data["error"] == "unknown city"
    assert "chur" in data["known"]
    assert fake_client.calls == [], "unknown input must never reach the upstream API"


def test_second_request_within_ttl_is_served_from_cache(client, fake_client):
    client.get("/api/weather")
    data = client.get("/api/weather").get_json()
    assert data["source"] == "cache"
    assert fake_client.calls == ["chur"]


def test_forecast_and_weather_share_one_upstream_call(client, fake_client):
    client.get("/api/weather")
    client.get("/api/forecast")
    assert fake_client.calls == ["chur"]


def test_expired_cache_triggers_a_new_fetch(client, fake_client, clock):
    client.get("/api/weather")
    clock.advance(901)
    fake_client.temperature = 7.0
    data = client.get("/api/weather").get_json()
    assert data["source"] == "upstream"
    assert data["current"]["temperature_c"] == 7.0
    assert len(fake_client.calls) == 2


def test_upstream_failure_serves_stale_data(client, fake_client, clock):
    client.get("/api/weather")
    clock.advance(901)
    fake_client.fail = True
    response = client.get("/api/weather")
    assert response.status_code == 200
    data = response.get_json()
    assert data["stale"] is True
    assert data["source"] == "stale"


def test_upstream_failure_without_cache_returns_503(client, fake_client):
    fake_client.fail = True
    response = client.get("/api/weather")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "60"
    assert response.get_json()["error"] == "weather data temporarily unavailable"


def test_storage_failure_returns_503(app, client):
    class DownRepository:
        def latest(self, city):
            raise RepositoryError("database unavailable")

    app.extensions["weather_service"]._repo = DownRepository()
    response = client.get("/api/weather")
    assert response.status_code == 503
    assert response.get_json()["error"] == "storage temporarily unavailable"


def test_forecast_defaults_to_three_days(client):
    data = client.get("/api/forecast").get_json()
    assert len(data["days"]) == 3
    assert data["days"][0]["description"] == "Leichter Regen"


def test_forecast_accepts_up_to_seven_days(client):
    assert len(client.get("/api/forecast?days=7").get_json()["days"]) == 7


@pytest.mark.parametrize("days", ["0", "8", "abc", "-1", "2.5"])
def test_forecast_rejects_invalid_days(client, days):
    response = client.get(f"/api/forecast?days={days}")
    assert response.status_code == 400
    assert "days" in response.get_json()["error"]


def test_history_is_empty_before_first_fetch(client):
    data = client.get("/api/history").get_json()
    assert data == {"location": data["location"], "count": 0, "items": []}


def test_history_lists_snapshots_newest_first(client, fake_client, clock):
    client.get("/api/weather")
    clock.advance(1000)
    fake_client.temperature = 9.0
    client.get("/api/weather")
    data = client.get("/api/history?limit=10").get_json()
    assert data["count"] == 2
    assert [item["current"]["temperature_c"] for item in data["items"]] == [9.0, 4.5]


def test_history_limit_is_validated(client):
    assert client.get("/api/history?limit=101").status_code == 400
    assert client.get("/api/history?limit=1").status_code == 200


def test_index_renders_weather_page(client):
    response = client.get("/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Wetter in Chur" in page
    assert "Bedeckt" in page
    assert "Open-Meteo" in page


def test_index_with_unknown_city_falls_back_to_default(client):
    response = client.get("/?city=<script>")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Wetter in Chur" in page
    assert "<script>" not in page


def test_index_shows_stale_hint(client, fake_client, clock):
    client.get("/")
    clock.advance(901)
    fake_client.fail = True
    assert "zuletzt gespeicherten" in client.get("/").get_data(as_text=True)


def test_index_shows_error_when_no_data(client, fake_client):
    fake_client.fail = True
    response = client.get("/?city=bern")
    assert response.status_code == 503
    assert "nicht verfügbar" in response.get_data(as_text=True)
