"""Phase 2 pipeline entry point: multi-series ALFRED ingest -> Snowflake RAW.

Run with `python -m ingest.pipeline_snowflake` (or `make run-snowflake`). Separate from
ingest/pipeline.py (the legacy single-series Postgres path), which keeps running unchanged
until this path is verified end to end — see CLAUDE.md's rule against deleting the Postgres
path in one pass.

Unlike the legacy pipeline, there is no data-quality gate here: RAW is deliberately
unvalidated (Phase 5 adds dbt tests once data reaches staging/marts). This pipeline's only
job is to land what FRED/ALFRED returned — completely, idempotently, and if any single series
fails to fetch, the whole run aborts rather than silently landing a partial pull (same
"never fabricate, never silently substitute" rule the legacy pipeline follows).
"""

from __future__ import annotations

import logging
import sys

from config import SnowflakeSettings, load_snowflake_settings
from db_snowflake import (
    init_schema,
    load_observations_current,
    load_observations_vintage,
    load_series_metadata,
    make_engine,
)
from ingest.fred import fetch_series_metadata, fetch_vintage_observations
from ingest.series import SERIES

log = logging.getLogger("bridge.pipeline_snowflake")


def run(settings: SnowflakeSettings) -> dict[str, int]:
    engine = make_engine(settings)
    init_schema(engine)

    totals = {"series": 0, "observations": 0}
    for series in SERIES:
        series_id = series["series_id"]
        vintage_tracked = series["vintage_tracked"]
        log.info("ingesting series=%s vintage_tracked=%s", series_id, vintage_tracked)

        meta = fetch_series_metadata(series_id, settings.fred_api_key)
        totals["series"] += load_series_metadata(engine, [meta])

        obs = fetch_vintage_observations(
            series_id, settings.fred_api_key, full_history=vintage_tracked
        )
        # Two different loaders, not two branches of the same one — see db_snowflake.py's
        # module docstring for why: the merge key genuinely differs depending on whether
        # these rows represent real ALFRED vintages or a same-stamped "current value" batch.
        loader = load_observations_vintage if vintage_tracked else load_observations_current
        n_obs = loader(engine, obs)
        totals["observations"] += n_obs
        log.info("series=%s: %d observation rows", series_id, n_obs)

    log.info(
        "done: %d series, %d observation rows loaded into RAW",
        totals["series"],
        totals["observations"],
    )
    return totals


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = load_snowflake_settings()
    if not settings.fred_api_key:
        log.error("FRED_API_KEY is not set (copy .env.example to .env)")
        sys.exit(2)
    if not (settings.account and settings.user and settings.password):
        log.error(
            "SNOWFLAKE_ACCOUNT/SNOWFLAKE_USER/SNOWFLAKE_PASSWORD are not fully set — "
            "run infra/snowflake_setup.sql and fill in .env first"
        )
        sys.exit(2)
    run(settings)


if __name__ == "__main__":
    main()
