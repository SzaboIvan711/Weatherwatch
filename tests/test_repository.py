import os
from datetime import UTC, datetime, timedelta

import pytest

from app.config import Config
from app.models import Snapshot
from app.repository import (
    MAX_SNAPSHOTS_PER_CITY,
    InMemorySnapshotRepository,
    PostgresSnapshotRepository,
    RepositoryError,
    create_repository,
)
from tests.conftest import make_report

T0 = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
UNREACHABLE_DSN = "postgresql://nobody:nothing@127.0.0.1:1/none"


def snap(city="chur", minutes=0, temperature=1.0):
    return Snapshot(
        city=city, fetched_at=T0 + timedelta(minutes=minutes), report=make_report(temperature)
    )


# --- in-memory ---------------------------------------------------------------


def test_memory_latest_and_history():
    repo = InMemorySnapshotRepository()
    assert repo.latest("chur") is None
    first = repo.save(snap(minutes=0, temperature=1.0))
    second = repo.save(snap(minutes=20, temperature=2.0))
    repo.save(snap(city="bern"))
    assert first.id == 1 and second.id == 2
    assert repo.latest("chur").report.current.temperature_c == 2.0
    assert [s.id for s in repo.history("chur", 10)] == [2, 1]
    assert len(repo.history("chur", 1)) == 1
    assert repo.healthy() is True


def test_memory_store_is_bounded_per_city():
    repo = InMemorySnapshotRepository()
    for i in range(MAX_SNAPSHOTS_PER_CITY + 5):
        repo.save(snap(minutes=i))
    assert len(repo.history("chur", MAX_SNAPSHOTS_PER_CITY + 100)) == MAX_SNAPSHOTS_PER_CITY


def test_create_repository_without_url_is_in_memory():
    config = Config(database_url=None, version="t", commit="c", log_level="INFO")
    assert isinstance(create_repository(config), InMemorySnapshotRepository)


# --- postgres, unreachable (no database needed) -------------------------------


def test_postgres_unreachable_reports_unhealthy_and_raises():
    repo = PostgresSnapshotRepository(UNREACHABLE_DSN, pool_timeout_seconds=0.3)
    try:
        assert repo.healthy() is False
        with pytest.raises(RepositoryError):
            repo.latest("chur")
    finally:
        repo.close()


def test_create_repository_with_url_is_postgres():
    config = Config(database_url=UNREACHABLE_DSN, version="t", commit="c", log_level="INFO")
    repo = create_repository(config)
    try:
        assert isinstance(repo, PostgresSnapshotRepository)
    finally:
        repo.close()


# --- postgres, real database (CI service container) ---------------------------

TEST_DSN = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def pg_repo():
    if not TEST_DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    repo = PostgresSnapshotRepository(TEST_DSN)
    assert repo.healthy()
    with repo._pool.connection() as conn:
        conn.execute("TRUNCATE weather_snapshots RESTART IDENTITY")
    yield repo
    repo.close()


@pytest.mark.integration
def test_postgres_round_trip(pg_repo):
    stored = pg_repo.save(snap(temperature=3.5))
    assert stored.id == 1
    latest = pg_repo.latest("chur")
    assert latest.report == stored.report
    assert latest.fetched_at == T0
    assert pg_repo.latest("bern") is None


@pytest.mark.integration
def test_postgres_history_newest_first_with_limit(pg_repo):
    for i in range(5):
        pg_repo.save(snap(minutes=i, temperature=float(i)))
    history = pg_repo.history("chur", 3)
    assert [s.report.current.temperature_c for s in history] == [4.0, 3.0, 2.0]


@pytest.mark.integration
def test_postgres_retention_removes_old_rows(pg_repo):
    old = Snapshot(
        city="chur", fetched_at=datetime.now(UTC) - timedelta(days=40), report=make_report()
    )
    pg_repo.save(old)
    pg_repo.save(Snapshot(city="chur", fetched_at=datetime.now(UTC), report=make_report()))
    assert len(pg_repo.history("chur", 10)) == 1


@pytest.mark.integration
def test_postgres_data_survives_a_new_repository_instance(pg_repo):
    pg_repo.save(snap(temperature=8.0))
    other = PostgresSnapshotRepository(TEST_DSN)
    try:
        assert other.latest("chur").report.current.temperature_c == 8.0
    finally:
        other.close()
