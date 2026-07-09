"""Warehouse access: schema, idempotent loads, and reads against Postgres.

SQLAlchemy Core (not the ORM) — the shapes are simple and the SQL stays visible,
which is the point of the "real DB ops" rep. Loads upsert on the (series_id,
date) primary key so re-running the pipeline is safe.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, text

from config import Settings

DDL = """
CREATE TABLE IF NOT EXISTS raw_observations (
    series_id  TEXT        NOT NULL,
    obs_date   DATE        NOT NULL,
    value      TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (series_id, obs_date)
);

CREATE TABLE IF NOT EXISTS clean_observations (
    series_id TEXT             NOT NULL,
    obs_date  DATE             NOT NULL,
    value     DOUBLE PRECISION NOT NULL,
    loaded_at TIMESTAMPTZ      NOT NULL DEFAULT now(),
    PRIMARY KEY (series_id, obs_date)
);
"""


def make_engine(settings: Settings) -> Engine:
    return create_engine(settings.database_url, future=True)


def ping(engine: Engine) -> bool:
    """True if the warehouse is reachable — used to skip integration tests."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def init_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for statement in filter(str.strip, DDL.split(";")):
            conn.execute(text(statement))


def load_raw(engine: Engine, rows: list[dict]) -> int:
    """Upsert raw string observations. Returns the number of rows sent."""
    if not rows:
        return 0
    stmt = text(
        """
        INSERT INTO raw_observations (series_id, obs_date, value)
        VALUES (:series_id, :date, :value)
        ON CONFLICT (series_id, obs_date)
        DO UPDATE SET value = EXCLUDED.value, fetched_at = now()
        """
    )
    with engine.begin() as conn:
        conn.execute(stmt, rows)
    return len(rows)


def load_clean(engine: Engine, rows: list[dict]) -> int:
    """Upsert clean typed observations. Returns the number of rows sent."""
    if not rows:
        return 0
    stmt = text(
        """
        INSERT INTO clean_observations (series_id, obs_date, value)
        VALUES (:series_id, :date, :value)
        ON CONFLICT (series_id, obs_date)
        DO UPDATE SET value = EXCLUDED.value, loaded_at = now()
        """
    )
    with engine.begin() as conn:
        conn.execute(stmt, rows)
    return len(rows)


def read_clean(engine: Engine, series_id: str) -> list[dict]:
    stmt = text(
        """
        SELECT series_id, obs_date AS date, value
        FROM clean_observations
        WHERE series_id = :series_id
        ORDER BY obs_date
        """
    )
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(stmt, {"series_id": series_id})]
