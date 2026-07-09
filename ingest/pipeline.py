"""Pipeline entry point: ingest -> raw table -> transform -> quality -> clean table.

Run with `python -m ingest.pipeline` (or `make run`). Reads config from the
environment / .env. Aborts (non-zero exit) if the data-quality gate fails, so a
bad pull never silently overwrites the clean table.
"""
from __future__ import annotations

import logging
import sys

from config import Settings, load_settings
from db import init_schema, load_clean, load_raw, make_engine
from ingest.fred import fetch_observations
from transform.quality import DataQualityError, run_all_checks
from transform.transform import transform

log = logging.getLogger("bridge.pipeline")

# Quality gate bounds for a full-history FRED series pull. Generous but real:
# DGS10 has ~16k business-day observations; freshness allows for weekends/holidays.
MIN_ROWS = 1_000
MAX_ROWS = 100_000
MAX_AGE_DAYS = 7


def run(settings: Settings) -> int:
    engine = make_engine(settings)
    init_schema(engine)

    log.info("ingesting series=%s", settings.fred_series_id)
    raw = fetch_observations(settings.fred_series_id, settings.fred_api_key)
    n_raw = load_raw(engine, raw)
    log.info("loaded %d raw observations", n_raw)

    clean = transform(raw)
    log.info("transformed -> %d clean observations", len(clean))

    run_all_checks(
        clean,
        min_rows=MIN_ROWS,
        max_rows=MAX_ROWS,
        max_age_days=MAX_AGE_DAYS,
    )
    log.info("data-quality checks passed")

    n_clean = load_clean(engine, clean)
    log.info("loaded %d clean observations into the warehouse", n_clean)
    return n_clean


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = load_settings()
    if not settings.fred_api_key:
        log.error("FRED_API_KEY is not set (copy .env.example to .env)")
        sys.exit(2)
    try:
        run(settings)
    except DataQualityError as exc:
        log.error("data-quality gate failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
