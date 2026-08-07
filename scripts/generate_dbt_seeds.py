"""Generate the dbt/seeds/*.csv fixtures from a live FRED/ALFRED pull.

These seeds are the DuckDB target's stand-in for Snowflake RAW: dbt-duckdb can't run the
production Python ingest pipeline itself, so `dbt seed --target duckdb` loads this snapshot
into the same `raw` schema/table names the `raw_fred` source expects (see
dbt/models/staging/_sources.yml) — the staging models don't know or care whether their source
data came from a live Snowflake table or a seeded CSV.

Deliberately trimmed to the last ~4 years (via FRED's observation_start), not full history —
this is a demo/dev fixture meant to be small enough to commit to git and load in under a
second, not a production data dump. The real pipeline (ingest/pipeline_snowflake.py) has no
such limit and pulls each series' full history when it runs against a live Snowflake account.
Re-run this script any time the fixture needs refreshing; it always overwrites both CSVs.

Usage: .venv/bin/python scripts/generate_dbt_seeds.py
"""

from __future__ import annotations

import csv
import datetime as dt
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import load_settings  # noqa: E402
from ingest.fred import fetch_series_metadata, fetch_vintage_observations  # noqa: E402
from ingest.series import SERIES  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("generate_dbt_seeds")

SEED_OBSERVATION_START = (
    "2022-08-05"  # ~4 years back — plenty to show real revisions, small enough to commit
)
SEEDS_DIR = Path(__file__).resolve().parent.parent / "dbt" / "seeds"

METADATA_COLUMNS = [
    "series_id",
    "title",
    "frequency",
    "units",
    "seasonal_adjustment",
    "observation_start",
    "observation_end",
    "fetched_at",
]
OBSERVATIONS_COLUMNS = [
    "series_id",
    "obs_date",
    "value",
    "realtime_start",
    "realtime_end",
    "fetched_at",
]


def main() -> None:
    settings = load_settings()
    if not settings.fred_api_key:
        log.error("FRED_API_KEY is not set (copy .env.example to .env)")
        sys.exit(2)

    fetched_at = dt.datetime.now(dt.UTC).isoformat()
    metadata_rows: list[dict] = []
    observation_rows: list[dict] = []

    for series in SERIES:
        series_id = series["series_id"]
        log.info("fetching series=%s vintage_tracked=%s", series_id, series["vintage_tracked"])

        meta = fetch_series_metadata(series_id, settings.fred_api_key)
        meta["fetched_at"] = fetched_at
        metadata_rows.append(meta)

        obs = fetch_vintage_observations(
            series_id,
            settings.fred_api_key,
            full_history=series["vintage_tracked"],
            observation_start=SEED_OBSERVATION_START,
        )
        for row in obs:
            row["fetched_at"] = fetched_at
        observation_rows.extend(obs)
        log.info(
            "series=%s: %d observation rows since %s", series_id, len(obs), SEED_OBSERVATION_START
        )

    SEEDS_DIR.mkdir(parents=True, exist_ok=True)

    # Filenames must match the table names _sources.yml declares (series_metadata,
    # observations) — dbt seed names tables after the CSV filename, and the `raw` schema
    # (dbt_project.yml's seeds config) is what already signals "this is RAW", so no redundant
    # raw_ prefix on the table name itself.
    meta_path = SEEDS_DIR / "series_metadata.csv"
    with meta_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=METADATA_COLUMNS)
        writer.writeheader()
        writer.writerows(metadata_rows)
    log.info("wrote %d rows -> %s", len(metadata_rows), meta_path)

    obs_path = SEEDS_DIR / "observations.csv"
    with obs_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OBSERVATIONS_COLUMNS)
        writer.writeheader()
        for row in observation_rows:
            out = {k: v for k, v in row.items() if k != "date"}
            out["obs_date"] = row["date"]
            writer.writerow(out)
    log.info("wrote %d rows -> %s", len(observation_rows), obs_path)


if __name__ == "__main__":
    main()
