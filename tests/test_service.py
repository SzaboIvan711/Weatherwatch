import threading
import time

from prometheus_client import CollectorRegistry

from app.locations import LOCATIONS
from app.metrics import AppMetrics
from app.repository import InMemorySnapshotRepository
from app.service import WeatherService
from tests.conftest import FakeClient, FakeClock, make_report


def build(ttl=900):
    registry = CollectorRegistry()
    client = FakeClient()
    service = WeatherService(
        repository=InMemorySnapshotRepository(),
        client=client,
        metrics=AppMetrics(registry),
        ttl_seconds=ttl,
        clock=FakeClock(),
    )
    return service, client, registry


def value(registry, name, **labels):
    return registry.get_sample_value(name, labels) or 0.0


def test_metrics_count_hits_misses_and_stale():
    service, client, registry = build(ttl=0)
    chur = LOCATIONS["chur"]
    service.get(chur)  # miss
    client.fail = True
    service.get(chur)  # ttl 0 -> refetch fails -> stale
    assert value(registry, "weatherwatch_cache_lookups_total", result="miss") == 1
    assert value(registry, "weatherwatch_cache_lookups_total", result="stale") == 1
    assert value(registry, "weatherwatch_upstream_requests_total", outcome="error") == 1
    assert value(registry, "weatherwatch_upstream_last_success_timestamp_seconds", city="chur") > 0


def test_concurrent_requests_fetch_upstream_only_once():
    service, _, _ = build()

    class SlowClient(FakeClient):
        def fetch(self, location):
            time.sleep(0.05)
            return super().fetch(location)

    slow = SlowClient()
    service._client = slow
    threads = [threading.Thread(target=service.get, args=(LOCATIONS["chur"],)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert slow.calls == ["chur"]


def test_history_delegates_to_repository():
    service, _, _ = build()
    service.get(LOCATIONS["bern"])
    assert len(service.history(LOCATIONS["bern"], 5)) == 1
    assert service.history(LOCATIONS["chur"], 5) == []


def test_make_report_helper_has_seven_days():
    assert len(make_report().daily) == 7
