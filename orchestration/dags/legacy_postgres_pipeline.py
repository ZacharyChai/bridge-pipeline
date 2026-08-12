"""TaskFlow DAG for the legacy single-series (DGS10) Postgres pipeline.

Wraps ingest/pipeline.py's existing fetch -> load_raw -> transform -> quality gate ->
load_clean sequence in three tasks instead of the single run() function the GCE box's
cron entry calls directly (deploy/bridge-pipeline.cron). No rewrite of the underlying
logic -- just re-wiring how it's triggered. See DECISIONS.md for why the live GCE cron
entry stays as-is rather than being pointed at this local Airflow instance.
"""

from __future__ import annotations

import logging

import pendulum
from airflow.sdk import dag, task
from callbacks import log_failure

log = logging.getLogger("airflow.task")

# Same bounds ingest/pipeline.py's run() uses for a full-history DGS10 pull.
MIN_ROWS = 1_000
MAX_ROWS = 100_000
MAX_AGE_DAYS = 7


@dag(
    dag_id="legacy_postgres_pipeline",
    description="FRED DGS10 ingest -> Postgres. Local demo of the GCE cron entry's job.",
    schedule="30 6 * * *",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    tags=["legacy", "postgres"],
    default_args={
        "retries": 3,
        "retry_delay": pendulum.duration(minutes=2),
        "retry_exponential_backoff": True,
        "max_retry_delay": pendulum.duration(minutes=20),
        "on_failure_callback": log_failure,
    },
)
def legacy_postgres_pipeline():
    @task
    def extract() -> list[dict]:
        """Fetch from FRED and land the raw pull. Retries live here specifically, not on
        the other tasks: the FRED HTTP call is the one genuinely flaky step, and a
        transform/load failure is a real bug a retry shouldn't paper over."""
        from config import load_settings
        from db import init_schema, load_raw, make_engine
        from ingest.fred import fetch_observations

        settings = load_settings()
        engine = make_engine(settings)
        init_schema(engine)

        raw = fetch_observations(settings.fred_series_id, settings.fred_api_key)
        n_raw = load_raw(engine, raw)
        log.info("extract: fetched and landed %d raw rows", n_raw)
        return raw

    @task
    def quality_gate(raw: list[dict]) -> list[dict]:
        """Pure transform + the data-quality gate. A violation raises DataQualityError,
        which fails the task outright -- a bad pull should never reach load()."""
        from transform.quality import run_all_checks
        from transform.transform import transform

        clean = transform(raw)
        run_all_checks(clean, min_rows=MIN_ROWS, max_rows=MAX_ROWS, max_age_days=MAX_AGE_DAYS)
        log.info("quality_gate: %d clean rows passed all checks", len(clean))
        # datetime.date isn't JSON-serializable for XCom -- pass it through as an ISO
        # string and convert back on the way into load().
        return [{**row, "date": row["date"].isoformat()} for row in clean]

    @task
    def load(clean: list[dict]) -> int:
        """Idempotency: load_clean() upserts on (series_id, date) (see db.py), so a
        rerun or backfill of this same day just re-writes the same rows -- safe by
        construction, no backfill-specific handling needed."""
        import datetime as dt

        from config import load_settings
        from db import load_clean, make_engine

        settings = load_settings()
        engine = make_engine(settings)
        rows = [{**row, "date": dt.date.fromisoformat(row["date"])} for row in clean]
        n = load_clean(engine, rows)
        log.info("load: upserted %d clean rows into the warehouse", n)
        return n

    load(quality_gate(extract()))


legacy_postgres_pipeline()
