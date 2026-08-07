"""Snowflake RAW-layer access: schema, idempotent loads.

Mirrors db.py's shape deliberately (SQLAlchemy Core, explicit DDL, idempotent loads) so the two
warehouses are easy to compare while both are live — see AUDIT.md and CLAUDE.md's rule against
deleting the Postgres path in one pass.

Everything here lands in RAW, verbatim: obs_date/value/realtime_start/realtime_end all stay
VARCHAR, exactly as FRED/ALFRED returned them — including FRED's "." missing-value marker.
Casting and cleaning are staging's job (Phase 3), not this module's. This is a stricter reading
of "raw means raw" than the legacy Postgres raw_observations table (which casts obs_date to a
native DATE) — see DECISIONS.md's Phase 2 entry.

Idempotency strategy: two loaders, because "vintage" means something different depending on
whether ingest/series.py's vintage_tracked flag is True or False for a given series.

- load_observations_vintage: for vintage_tracked=True series, keyed on
  (series_id, obs_date, realtime_start). ALFRED vintage data means a single observation date
  can have many rows — one per real revision — and realtime_start is immutable per vintage
  once published; realtime_end is the one field that legitimately changes on a later pull (it
  closes off when a newer vintage supersedes it).
- load_observations_current: for vintage_tracked=False series (the daily market-rate ones —
  see DECISIONS.md's Phase 2 entry), keyed on (series_id, obs_date) alone. These are fetched
  without a wide realtime window, so FRED stamps every row with realtime_start=realtime_end=
  "today" — a fixed value for the whole pull, not tied to any real revision. Merging on the
  3-column key here would be a bug: tomorrow's pull re-stamps every row with tomorrow's date,
  which wouldn't match today's rows, so the pipeline would insert a full duplicate batch every
  day instead of updating the "latest known value" in place. (Found this the hard way — see
  DECISIONS.md.) realtime_start/realtime_end are still stored, just as "last checked on" info,
  not as part of the row's identity.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, text

from config import SnowflakeSettings

SERIES_METADATA_DDL = """
CREATE TABLE IF NOT EXISTS RAW.SERIES_METADATA (
    series_id            VARCHAR NOT NULL,
    title                VARCHAR,
    frequency            VARCHAR,
    units                VARCHAR,
    seasonal_adjustment  VARCHAR,
    observation_start    VARCHAR,
    observation_end      VARCHAR,
    fetched_at           TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (series_id)
)
"""

OBSERVATIONS_DDL = """
CREATE TABLE IF NOT EXISTS RAW.OBSERVATIONS (
    series_id       VARCHAR NOT NULL,
    obs_date        VARCHAR NOT NULL,
    value           VARCHAR,
    realtime_start  VARCHAR NOT NULL,
    realtime_end    VARCHAR NOT NULL,
    fetched_at      TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (series_id, obs_date, realtime_start)
)
"""


def make_engine(settings: SnowflakeSettings) -> Engine:
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
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS RAW"))
        conn.execute(text(SERIES_METADATA_DDL))
        conn.execute(text(OBSERVATIONS_DDL))


def load_series_metadata(engine: Engine, rows: list[dict]) -> int:
    """Upsert series metadata, keyed on series_id. Returns the number of rows sent."""
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TEMPORARY TABLE IF NOT EXISTS RAW._stg_series_metadata (
                    series_id VARCHAR, title VARCHAR, frequency VARCHAR, units VARCHAR,
                    seasonal_adjustment VARCHAR, observation_start VARCHAR, observation_end VARCHAR
                )
                """
            )
        )
        conn.execute(text("TRUNCATE TABLE RAW._stg_series_metadata"))
        conn.execute(
            text(
                """
                INSERT INTO RAW._stg_series_metadata
                    (series_id, title, frequency, units, seasonal_adjustment,
                     observation_start, observation_end)
                VALUES
                    (:series_id, :title, :frequency, :units, :seasonal_adjustment,
                     :observation_start, :observation_end)
                """
            ),
            rows,
        )
        conn.execute(
            text(
                """
                MERGE INTO RAW.SERIES_METADATA AS t
                USING RAW._stg_series_metadata AS s
                ON t.series_id = s.series_id
                WHEN MATCHED THEN UPDATE SET
                    title = s.title,
                    frequency = s.frequency,
                    units = s.units,
                    seasonal_adjustment = s.seasonal_adjustment,
                    observation_start = s.observation_start,
                    observation_end = s.observation_end,
                    fetched_at = CURRENT_TIMESTAMP()
                WHEN NOT MATCHED THEN INSERT
                    (series_id, title, frequency, units, seasonal_adjustment,
                     observation_start, observation_end)
                    VALUES
                    (s.series_id, s.title, s.frequency, s.units, s.seasonal_adjustment,
                     s.observation_start, s.observation_end)
                """
            )
        )
    return len(rows)


def load_observations_vintage(engine: Engine, rows: list[dict]) -> int:
    """Upsert vintage observations, keyed on (series_id, obs_date, realtime_start).
    Returns the number of rows sent."""
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TEMPORARY TABLE IF NOT EXISTS RAW._stg_observations (
                    series_id VARCHAR, obs_date VARCHAR, value VARCHAR,
                    realtime_start VARCHAR, realtime_end VARCHAR
                )
                """
            )
        )
        conn.execute(text("TRUNCATE TABLE RAW._stg_observations"))
        conn.execute(
            text(
                """
                INSERT INTO RAW._stg_observations
                    (series_id, obs_date, value, realtime_start, realtime_end)
                VALUES
                    (:series_id, :date, :value, :realtime_start, :realtime_end)
                """
            ),
            rows,
        )
        conn.execute(
            text(
                """
                MERGE INTO RAW.OBSERVATIONS AS t
                USING RAW._stg_observations AS s
                ON t.series_id = s.series_id
                   AND t.obs_date = s.obs_date
                   AND t.realtime_start = s.realtime_start
                WHEN MATCHED THEN UPDATE SET
                    value = s.value,
                    realtime_end = s.realtime_end,
                    fetched_at = CURRENT_TIMESTAMP()
                WHEN NOT MATCHED THEN INSERT
                    (series_id, obs_date, value, realtime_start, realtime_end)
                    VALUES
                    (s.series_id, s.obs_date, s.value, s.realtime_start, s.realtime_end)
                """
            )
        )
    return len(rows)


def load_observations_current(engine: Engine, rows: list[dict]) -> int:
    """Upsert current-value-only observations, keyed on (series_id, obs_date) alone — see the
    module docstring for why this needs a different key than load_observations_vintage.
    Returns the number of rows sent."""
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TEMPORARY TABLE IF NOT EXISTS RAW._stg_observations_current (
                    series_id VARCHAR, obs_date VARCHAR, value VARCHAR,
                    realtime_start VARCHAR, realtime_end VARCHAR
                )
                """
            )
        )
        conn.execute(text("TRUNCATE TABLE RAW._stg_observations_current"))
        conn.execute(
            text(
                """
                INSERT INTO RAW._stg_observations_current
                    (series_id, obs_date, value, realtime_start, realtime_end)
                VALUES
                    (:series_id, :date, :value, :realtime_start, :realtime_end)
                """
            ),
            rows,
        )
        conn.execute(
            text(
                """
                MERGE INTO RAW.OBSERVATIONS AS t
                USING RAW._stg_observations_current AS s
                ON t.series_id = s.series_id
                   AND t.obs_date = s.obs_date
                WHEN MATCHED THEN UPDATE SET
                    value = s.value,
                    realtime_start = s.realtime_start,
                    realtime_end = s.realtime_end,
                    fetched_at = CURRENT_TIMESTAMP()
                WHEN NOT MATCHED THEN INSERT
                    (series_id, obs_date, value, realtime_start, realtime_end)
                    VALUES
                    (s.series_id, s.obs_date, s.value, s.realtime_start, s.realtime_end)
                """
            )
        )
    return len(rows)


def read_observations(engine: Engine, series_id: str) -> list[dict]:
    stmt = text(
        """
        SELECT series_id, obs_date, value, realtime_start, realtime_end
        FROM RAW.OBSERVATIONS
        WHERE series_id = :series_id
        ORDER BY obs_date, realtime_start
        """
    )
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(stmt, {"series_id": series_id})]
