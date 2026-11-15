"""Application-specific Prometheus metrics.

HTTP request count and latency come from prometheus-flask-exporter
(flask_http_request_total, flask_http_request_duration_seconds). The metrics
here describe what is special about this app: the cache and the upstream API.
Label values are bounded (fixed outcomes, allow-listed cities).
"""

from __future__ import annotations

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram


class AppMetrics:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        registry = registry or REGISTRY
        self.cache_lookups = Counter(
            "weatherwatch_cache_lookups_total",
            "Cache lookups by result (hit, miss, stale)",
            ["result"],
            registry=registry,
        )
        self.upstream_requests = Counter(
            "weatherwatch_upstream_requests_total",
            "Requests to the weather API by outcome (success, error)",
            ["outcome"],
            registry=registry,
        )
        self.upstream_duration = Histogram(
            "weatherwatch_upstream_request_duration_seconds",
            "Duration of requests to the weather API, including retries",
            buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0),
            registry=registry,
        )
        self.last_success = Gauge(
            "weatherwatch_upstream_last_success_timestamp_seconds",
            "Unix time of the last successful fetch per city",
            ["city"],
            registry=registry,
        )
        for result in ("hit", "miss", "stale"):
            self.cache_lookups.labels(result=result)
        for outcome in ("success", "error"):
            self.upstream_requests.labels(outcome=outcome)
