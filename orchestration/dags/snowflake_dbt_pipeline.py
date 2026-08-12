"""TaskFlow DAG for the Phase 2+ Snowflake pipeline: vintage-aware FRED/ALFRED ingest
into RAW, then a dbt build on top of it.

This is the pipeline README.md and INTERVIEW_NOTES.md flagged as unscheduled ("no
scheduled ingestion for the Snowflake path", Phase 8). See DECISIONS.md for why Airflow
ended up here instead of the Dagster asset-graph originally sketched for that phase.
"""

from __future__ import annotations

import logging
import subprocess

import pendulum
from airflow.sdk import dag, task
from callbacks import log_failure

log = logging.getLogger("airflow.task")

DBT_PROJECT_DIR = "/opt/airflow/bridge-pipeline/dbt"


@dag(
    dag_id="snowflake_dbt_pipeline",
    description="FRED/ALFRED vintage ingest -> Snowflake RAW -> dbt build (staging + marts).",
    schedule="30 6 * * *",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    tags=["snowflake", "dbt"],
    default_args={
        "retries": 3,
        "retry_delay": pendulum.duration(minutes=2),
        "retry_exponential_backoff": True,
        "max_retry_delay": pendulum.duration(minutes=20),
        "on_failure_callback": log_failure,
    },
)
def snowflake_dbt_pipeline():
    @task
    def ingest_series() -> dict[str, int]:
        """All 17 series, one task -- ingest.pipeline_snowflake.run() already aborts the
        whole call if any single series fails to fetch (see its docstring), so retrying
        this task re-attempts one clean, complete pull rather than patching a partial
        one. Idempotency: every run re-fetches full current state per series (vintage
        history for the 10 tracked series, current value for the rest) and MERGEs it in
        -- a scheduler-triggered rerun or manual backfill lands the same end state as a
        single run, by construction, not because of backfill-specific logic here."""
        from config import load_snowflake_settings
        from ingest.pipeline_snowflake import run

        settings = load_snowflake_settings()
        totals = run(settings)
        log.info("ingest_series: %s", totals)
        return totals

    @task
    def dbt_build(totals: dict[str, int]) -> None:
        log.info("dbt build starting after ingest: %s", totals)
        try:
            result = subprocess.run(
                [
                    "dbt",
                    "build",
                    "--project-dir",
                    DBT_PROJECT_DIR,
                    "--profiles-dir",
                    DBT_PROJECT_DIR,
                    "--target",
                    "snowflake",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            # dbt's own error-severity tests already fail the run via a non-zero exit
            # (see dbt/models/marts/_marts.yml's deliberate warn/error split) -- this
            # just makes sure the actual dbt output lands in the Airflow task log
            # instead of being swallowed by the exception's default repr.
            log.error("dbt build failed:\nstdout:\n%s\nstderr:\n%s", exc.stdout, exc.stderr)
            raise
        log.info(result.stdout)

    dbt_build(ingest_series())


snowflake_dbt_pipeline()
