"""Storage for weather snapshots: in-memory (default) or PostgreSQL.

Every successful upstream fetch is stored as one snapshot. The newest snapshot
of a city is the cache entry; all snapshots together form the history.
Routes and the service depend on the SnapshotRepository protocol only.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Protocol

from app.config import Config
from app.models import Snapshot, WeatherReport

log = logging.getLogger(__name__)

# Upper bound per city for the in-memory store and the retention window in
# Postgres. Keeps storage bounded no matter how long the app runs.
MAX_SNAPSHOTS_PER_CITY = 500
RETENTION_DAYS = 30


class RepositoryError(RuntimeError):
    """The storage backend is unavailable or failed."""


class SnapshotRepository(Protocol):
    def save(self, snapshot: Snapshot) -> Snapshot: ...
    def latest(self, city: str) -> Snapshot | None: ...
    def history(self, city: str, limit: int) -> list[Snapshot]: ...
    def healthy(self) -> bool: ...


class InMemorySnapshotRepository:
    """Per-process store. Lost on restart, not shared between processes."""

    backend = "memory"

    def __init__(self) -> None:
        self._data: dict[str, deque[Snapshot]] = {}
        self._next_id = 1
        self._lock = threading.Lock()

    def save(self, snapshot: Snapshot) -> Snapshot:
        with self._lock:
            stored = Snapshot(
                city=snapshot.city,
                fetched_at=snapshot.fetched_at,
                report=snapshot.report,
                id=self._next_id,
            )
            self._next_id += 1
            self._data.setdefault(snapshot.city, deque(maxlen=MAX_SNAPSHOTS_PER_CITY)).append(
                stored
            )
            return stored

    def latest(self, city: str) -> Snapshot | None:
        with self._lock:
            entries = self._data.get(city)
            return entries[-1] if entries else None

    def history(self, city: str, limit: int) -> list[Snapshot]:
        with self._lock:
            entries = list(self._data.get(city, ()))
        return list(reversed(entries))[:limit]

    def healthy(self) -> bool:
        return True


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS weather_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    city        TEXT        NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL,
    payload     JSONB       NOT NULL
);
CREATE INDEX IF NOT EXISTS weather_snapshots_city_fetched_at_idx
    ON weather_snapshots (city, fetched_at DESC);
"""


class PostgresSnapshotRepository:
    """Shared, durable store. Used by Compose, Kubernetes and optionally Render."""

    backend = "postgres"

    def __init__(self, dsn: str, pool_timeout_seconds: float = 5.0) -> None:
        import psycopg
        from psycopg_pool import ConnectionPool

        self._errors: tuple[type[BaseException], ...] = (psycopg.Error, OSError)
        try:
            from psycopg_pool import PoolTimeout

            self._errors = (*self._errors, PoolTimeout)
        except ImportError:  # pragma: no cover - older psycopg_pool
            pass

        from psycopg.types.json import Jsonb

        self._jsonb = Jsonb
        # open=False + open(wait=False): the app starts even when the database
        # is not reachable yet. /ready reports 503 until it is, and Kubernetes
        # keeps the pod out of the Service meanwhile.
        self._pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=5,
            timeout=pool_timeout_seconds,
            kwargs={"connect_timeout": 3, "application_name": "weatherwatch"},
            open=False,
        )
        self._pool.open(wait=False)
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            with self._pool.connection() as conn:
                # Several replicas may start at the same time; serialise the
                # DDL with an advisory lock so CREATE ... IF NOT EXISTS does
                # not race on the catalog.
                conn.execute("SELECT pg_advisory_xact_lock(4242)")
                conn.execute(SCHEMA_SQL)
            self._schema_ready = True
            log.info("database schema ready")

    def _run(self, operation):
        try:
            self._ensure_schema()
            with self._pool.connection() as conn:
                return operation(conn)
        except self._errors as exc:
            log.error("database operation failed: %s", type(exc).__name__)
            raise RepositoryError("database unavailable") from exc

    @staticmethod
    def _row_to_snapshot(row) -> Snapshot:
        snapshot_id, city, fetched_at, payload = row
        return Snapshot(
            id=snapshot_id,
            city=city,
            fetched_at=fetched_at.astimezone(UTC),
            report=WeatherReport.from_dict(payload),
        )

    def save(self, snapshot: Snapshot) -> Snapshot:
        def op(conn):
            row = conn.execute(
                "INSERT INTO weather_snapshots (city, fetched_at, payload) "
                "VALUES (%s, %s, %s) RETURNING id, city, fetched_at, payload",
                (snapshot.city, snapshot.fetched_at, self._jsonb(snapshot.report.to_dict())),
            ).fetchone()
            conn.execute(
                "DELETE FROM weather_snapshots "
                "WHERE city = %s AND fetched_at < now() - make_interval(days => %s)",
                (snapshot.city, RETENTION_DAYS),
            )
            return row

        return self._row_to_snapshot(self._run(op))

    def latest(self, city: str) -> Snapshot | None:
        row = self._run(
            lambda conn: conn.execute(
                "SELECT id, city, fetched_at, payload FROM weather_snapshots "
                "WHERE city = %s ORDER BY fetched_at DESC, id DESC LIMIT 1",
                (city,),
            ).fetchone()
        )
        return self._row_to_snapshot(row) if row else None

    def history(self, city: str, limit: int) -> list[Snapshot]:
        rows = self._run(
            lambda conn: conn.execute(
                "SELECT id, city, fetched_at, payload FROM weather_snapshots "
                "WHERE city = %s ORDER BY fetched_at DESC, id DESC LIMIT %s",
                (city, limit),
            ).fetchall()
        )
        return [self._row_to_snapshot(row) for row in rows]

    def healthy(self) -> bool:
        try:
            self._run(lambda conn: conn.execute("SELECT 1").fetchone())
            return True
        except RepositoryError:
            return False

    def close(self) -> None:
        self._pool.close()


def create_repository(config: Config) -> SnapshotRepository:
    if config.database_url:
        log.info("using postgres repository")
        return PostgresSnapshotRepository(config.database_url)
    log.warning(
        "no DATABASE_URL set, using in-memory repository: "
        "history is per-process and is lost on restart"
    )
    return InMemorySnapshotRepository()


def utcnow() -> datetime:
    return datetime.now(UTC)
