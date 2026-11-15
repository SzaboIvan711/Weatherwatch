from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request

from app.locations import LOCATIONS, Location, UnknownLocationError, resolve
from app.repository import RepositoryError
from app.service import WeatherResult, WeatherService, WeatherUnavailableError

log = logging.getLogger(__name__)

bp = Blueprint("main", __name__)

ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
DEFAULT_FORECAST_DAYS = 3
MAX_FORECAST_DAYS = 7
DEFAULT_HISTORY_LIMIT = 20
MAX_HISTORY_LIMIT = 100


class ValidationError(ValueError):
    """Client input is malformed. Mapped to HTTP 400."""


def _service() -> WeatherService:
    return current_app.extensions["weather_service"]


def _config():
    return current_app.extensions["app_config"]


def _location() -> Location:
    return resolve(request.args.get("city"), _config().default_city)


def _int_arg(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    if not raw.isdigit():
        raise ValidationError(f"{name} must be a positive integer")
    value = int(raw)
    if not minimum <= value <= maximum:
        raise ValidationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _envelope(result: WeatherResult, location: Location) -> dict[str, Any]:
    return {
        "location": location.to_dict(),
        "fetched_at": result.snapshot.fetched_at.isoformat(),
        "source": result.source,
        "stale": result.stale,
        "attribution": ATTRIBUTION,
    }


# --- error mapping ----------------------------------------------------------


@bp.app_errorhandler(ValidationError)
def _bad_request(exc: ValidationError):
    return jsonify(error=str(exc)), 400


@bp.app_errorhandler(UnknownLocationError)
def _unknown_location(exc: UnknownLocationError):
    return jsonify(error="unknown city", known=sorted(LOCATIONS)), 404


@bp.app_errorhandler(WeatherUnavailableError)
def _weather_unavailable(exc: WeatherUnavailableError):
    response = jsonify(error="weather data temporarily unavailable")
    response.headers["Retry-After"] = "60"
    return response, 503


@bp.app_errorhandler(RepositoryError)
def _storage_unavailable(exc: RepositoryError):
    response = jsonify(error="storage temporarily unavailable")
    response.headers["Retry-After"] = "30"
    return response, 503


# --- operational endpoints --------------------------------------------------


@bp.get("/health")
def health():
    """Liveness: is the process up? Never touches the database or the API.

    Kubernetes restarts the container when this fails; a slow dependency must
    never be able to trigger a restart loop.
    """
    config = _config()
    return jsonify(status="ok", version=config.version, commit=config.commit)


@bp.get("/ready")
def ready():
    """Readiness: may this instance receive traffic? Checks the storage."""
    repo = current_app.extensions["repository"]
    if repo.healthy():
        return jsonify(status="ready", storage=getattr(repo, "backend", "unknown"))
    return jsonify(status="unavailable"), 503


# --- domain API --------------------------------------------------------------


@bp.get("/api/locations")
def list_locations():
    return jsonify(
        default=_config().default_city,
        locations=[loc.to_dict() for loc in LOCATIONS.values()],
    )


@bp.get("/api/weather")
def current_weather():
    location = _location()
    result = _service().get(location)
    return jsonify(
        **_envelope(result, location),
        current=result.snapshot.report.current.to_dict(),
    )


@bp.get("/api/forecast")
def forecast():
    location = _location()
    days = _int_arg("days", DEFAULT_FORECAST_DAYS, 1, MAX_FORECAST_DAYS)
    result = _service().get(location)
    return jsonify(
        **_envelope(result, location),
        days=[day.to_dict() for day in result.snapshot.report.daily[:days]],
    )


@bp.get("/api/history")
def history():
    location = _location()
    limit = _int_arg("limit", DEFAULT_HISTORY_LIMIT, 1, MAX_HISTORY_LIMIT)
    snapshots = _service().history(location, limit)
    return jsonify(
        location=location.to_dict(),
        count=len(snapshots),
        items=[
            {
                "id": snap.id,
                "fetched_at": snap.fetched_at.isoformat(),
                "current": snap.report.current.to_dict(),
            }
            for snap in snapshots
        ],
    )


# --- HTML page ---------------------------------------------------------------


@bp.get("/")
def index():
    config = _config()
    try:
        location = _location()
    except UnknownLocationError:
        location = resolve(None, config.default_city)

    result: WeatherResult | None = None
    error: str | None = None
    try:
        result = _service().get(location)
    except (WeatherUnavailableError, RepositoryError):
        error = "Die Wetterdaten sind im Moment nicht verfügbar. Bitte später erneut versuchen."

    status = 200 if result else 503
    return (
        render_template(
            "index.html",
            version=config.version,
            location=location,
            locations=LOCATIONS.values(),
            result=result,
            forecast=result.snapshot.report.daily[:DEFAULT_FORECAST_DAYS] if result else [],
            error=error,
            attribution=ATTRIBUTION,
        ),
        status,
    )
