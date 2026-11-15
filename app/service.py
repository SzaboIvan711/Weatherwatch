"""Read-through cache in front of the weather API.

Decision table for one request:

    newest snapshot younger than TTL      -> serve it            (cache hit)
    otherwise fetch upstream and store it -> serve it            (cache miss)
    upstream fails, an older snapshot     -> serve it, stale=true (degraded)
    upstream fails, nothing stored        -> WeatherUnavailableError (503)

A per-city lock makes sure that, when an entry expires under load, only one
request per process calls the upstream API; the others wait and then read the
fresh snapshot. This protects the free upstream service from bursts.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.locations import Location
from app.metrics import AppMetrics
from app.models import Snapshot
from app.repository import SnapshotRepository, utcnow
from app.weather import WeatherClient, WeatherProviderError

log = logging.getLogger(__name__)


class WeatherUnavailableError(RuntimeError):
    """No fresh data from upstream and nothing cached to fall back on."""


@dataclass(frozen=True)
class WeatherResult:
    snapshot: Snapshot
    source: str  # "cache", "upstream" or "stale"

    @property
    def stale(self) -> bool:
        return self.source == "stale"


class WeatherService:
    def __init__(
        self,
        repository: SnapshotRepository,
        client: WeatherClient,
        metrics: AppMetrics,
        ttl_seconds: int,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._repo = repository
        self._client = client
        self._metrics = metrics
        self._ttl = ttl_seconds
        self._clock = clock
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, city: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(city, threading.Lock())

    def _fresh(self, snapshot: Snapshot | None) -> bool:
        return snapshot is not None and snapshot.age_seconds(self._clock()) < self._ttl

    def get(self, location: Location) -> WeatherResult:
        cached = self._repo.latest(location.slug)
        if self._fresh(cached):
            self._metrics.cache_lookups.labels(result="hit").inc()
            return WeatherResult(cached, "cache")

        with self._lock_for(location.slug):
            # Another thread may have refreshed the entry while we waited.
            cached = self._repo.latest(location.slug)
            if self._fresh(cached):
                self._metrics.cache_lookups.labels(result="hit").inc()
                return WeatherResult(cached, "cache")

            started = time.perf_counter()
            try:
                report = self._client.fetch(location)
            except WeatherProviderError as exc:
                self._metrics.upstream_requests.labels(outcome="error").inc()
                self._metrics.upstream_duration.observe(time.perf_counter() - started)
                if cached is not None:
                    self._metrics.cache_lookups.labels(result="stale").inc()
                    log.warning("serving stale data for %s: %s", location.slug, exc)
                    return WeatherResult(cached, "stale")
                raise WeatherUnavailableError(str(exc)) from exc

            self._metrics.upstream_requests.labels(outcome="success").inc()
            self._metrics.upstream_duration.observe(time.perf_counter() - started)
            self._metrics.cache_lookups.labels(result="miss").inc()

            stored = self._repo.save(
                Snapshot(city=location.slug, fetched_at=self._clock(), report=report)
            )
            self._metrics.last_success.labels(city=location.slug).set(stored.fetched_at.timestamp())
            return WeatherResult(stored, "upstream")

    def history(self, location: Location, limit: int) -> list[Snapshot]:
        return self._repo.history(location.slug, limit)
