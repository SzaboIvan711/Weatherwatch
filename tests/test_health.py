def test_health_reports_ok_version_and_commit(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "version": "test", "commit": "abc123def4567890"}


def test_health_does_not_touch_storage(app, client):
    class ExplodingRepository:
        def __getattr__(self, name):
            raise AssertionError("liveness must not use the repository")

    app.extensions["repository"] = ExplodingRepository()
    assert client.get("/health").status_code == 200


def test_ready_with_in_memory_repository(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ready", "storage": "memory"}


def test_ready_returns_503_when_storage_is_unhealthy(app, client):
    class BrokenRepository:
        def healthy(self):
            return False

    app.extensions["repository"] = BrokenRepository()
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.get_json()["status"] == "unavailable"


def test_metrics_exposes_app_and_http_metrics(client):
    client.get("/api/weather")
    body = client.get("/metrics").get_data(as_text=True)
    assert 'weatherwatch_info{commit="abc123def456",version="test"}' in body
    assert "flask_http_request_total" in body
    assert 'weatherwatch_cache_lookups_total{result="miss"} 1.0' in body
    assert 'weatherwatch_upstream_requests_total{outcome="success"} 1.0' in body
    assert "weatherwatch_upstream_request_duration_seconds_bucket" in body


def test_metrics_group_unknown_paths_into_one_series(client):
    for path in ("/nope-1", "/nope-2", "/nope-3"):
        client.get(path)
    body = client.get("/metrics").get_data(as_text=True)
    assert "nope-1" not in body


def test_security_headers_are_set(client):
    headers = client.get("/health").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in headers["Content-Security-Policy"]


def test_unknown_route_returns_json_404(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.get_json() == {"error": "not found"}


def test_wrong_method_returns_json_405(client):
    response = client.post("/api/weather")
    assert response.status_code == 405
    assert response.get_json() == {"error": "method not allowed"}


def test_unexpected_error_returns_json_500_without_details(app, client):
    class CrashingService:
        def get(self, location):
            raise RuntimeError("secret internals")

    app.extensions["weather_service"] = CrashingService()
    response = client.get("/api/weather")
    assert response.status_code == 500
    assert response.get_json() == {"error": "internal server error"}
    assert b"secret internals" not in response.data
