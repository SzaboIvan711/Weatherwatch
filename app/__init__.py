from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from flask import Flask, jsonify
from prometheus_client import CollectorRegistry
from prometheus_flask_exporter import PrometheusMetrics
from werkzeug.exceptions import HTTPException

from app.config import Config
from app.metrics import AppMetrics
from app.repository import SnapshotRepository, create_repository, utcnow
from app.service import WeatherService
from app.weather import OpenMeteoClient, WeatherClient

log = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'self'; img-src 'self'; "
        "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    ),
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}


def create_app(
    config: Config | None = None,
    repository: SnapshotRepository | None = None,
    client: WeatherClient | None = None,
    registry: CollectorRegistry | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> Flask:
    """Application factory.

    Every dependency can be injected; the test suite uses this to run without
    network, database or the global Prometheus registry. `registry` defaults to
    the global registry; tests pass a fresh one per app, otherwise a second
    create_app() would register the same metric names twice.
    """
    config = config or Config.from_env()

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = Flask(__name__)
    # No request bodies are accepted anywhere; cap them anyway.
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    app.json.sort_keys = False

    repository = repository or create_repository(config)
    client = client or OpenMeteoClient(
        base_url=config.weather_api_url,
        api_key=config.weather_api_key,
        timeout_seconds=config.http_timeout_seconds,
    )

    # group_by="url_rule" keeps label cardinality bounded: requests to random
    # unknown paths are all counted under one label value instead of one
    # time series per path.
    metrics = PrometheusMetrics(
        app,
        registry=registry,
        group_by="url_rule",
        excluded_paths=["^/metrics$"],
    )
    metrics.info(
        "weatherwatch_info",
        "Application info",
        version=config.version,
        commit=config.commit[:12],
    )
    app_metrics = AppMetrics(registry)

    app.extensions["app_config"] = config
    app.extensions["repository"] = repository
    app.extensions["weather_service"] = WeatherService(
        repository=repository,
        client=client,
        metrics=app_metrics,
        ttl_seconds=config.cache_ttl_seconds,
        clock=clock,
    )

    from app.routes import bp

    app.register_blueprint(bp)

    @app.after_request
    def _security_headers(response):
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        return jsonify(error=exc.name.lower()), exc.code

    @app.errorhandler(Exception)
    def _unexpected_error(exc: Exception):
        log.exception("unhandled error")
        return jsonify(error="internal server error"), 500

    log.info(
        "weatherwatch %s (%s) started, storage=%s, cache_ttl=%ss",
        config.version,
        config.commit[:12],
        getattr(repository, "backend", "custom"),
        config.cache_ttl_seconds,
    )
    return app
