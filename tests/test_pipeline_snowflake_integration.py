"""Phase 2 integration: prove the Snowflake RAW loader is idempotent and handles revisions.

Skipped automatically when no Snowflake account is reachable (mirrors
test_pipeline_integration.py's pattern for Postgres) — so the unit suite stays green
anywhere, and this runs for real once SNOWFLAKE_* env vars point at a live account
(see infra/snowflake_setup.sql).
"""

import pytest
from sqlalchemy import text

from config import load_snowflake_settings
from db_snowflake import make_engine, ping

pytestmark = pytest.mark.integration

# RAW is shared with the real pipeline (ingest/pipeline_snowflake.py writes the same tables) —
# these IDs exist only so tests have something to key on that can never collide with a real
# FRED series_id, and every test that writes one cleans it up in a finally block. Without that,
# a test run leaves rows sitting in production RAW indefinitely (this happened once — see
# DECISIONS.md's Phase 2 entry).
TEST_META_ID = "TEST_META"
TEST_VINTAGE_ID = "TEST_VINTAGE"
TEST_CURRENT_ID = "TEST_CURRENT"


@pytest.fixture(scope="module")
def engine():
    settings = load_snowflake_settings()
    if not (settings.account and settings.user and settings.password):
        pytest.skip("SNOWFLAKE_* env vars not set — run infra/snowflake_setup.sql first")
    eng = make_engine(settings)
    if not ping(eng):
        pytest.skip("no Snowflake account reachable with the configured SNOWFLAKE_* env vars")
    return eng


def _delete_test_rows(engine, series_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM RAW.SERIES_METADATA WHERE series_id = :sid"), {"sid": series_id}
        )
        conn.execute(
            text("DELETE FROM RAW.OBSERVATIONS WHERE series_id = :sid"), {"sid": series_id}
        )


def test_series_metadata_upsert_is_idempotent(engine):
    from db_snowflake import init_schema, load_series_metadata

    init_schema(engine)

    meta = {
        "series_id": TEST_META_ID,
        "title": "Test Series",
        "frequency": "D",
        "units": "%",
        "seasonal_adjustment": "NSA",
        "observation_start": "2020-01-01",
        "observation_end": "2026-01-01",
    }
    try:
        load_series_metadata(engine, [meta])
        n_second = load_series_metadata(engine, [meta])  # repeat load, same row

        assert n_second == 1  # merge processed it, didn't error or skip

        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT count(*) AS n FROM RAW.SERIES_METADATA WHERE series_id = :sid"),
                {"sid": TEST_META_ID},
            ).fetchone()
        assert rows.n == 1  # not duplicated
    finally:
        _delete_test_rows(engine, TEST_META_ID)


def test_observations_vintage_upsert_handles_revisions(engine):
    from db_snowflake import init_schema, load_observations_vintage, read_observations

    init_schema(engine)

    try:
        # first pull: one open vintage for 2025-12-01
        first_pull = [
            {
                "series_id": TEST_VINTAGE_ID,
                "date": "2025-12-01",
                "value": "3.10",
                "realtime_start": "2026-01-15",
                "realtime_end": "9999-12-31",
            }
        ]
        load_observations_vintage(engine, first_pull)

        # second pull: FRED published a revision. The old vintage's realtime_end closes,
        # and a new vintage row appears — this is exactly what a later `dbt build` needs
        # for point-in-time correctness (Phase 4).
        second_pull = [
            {
                "series_id": TEST_VINTAGE_ID,
                "date": "2025-12-01",
                "value": "3.10",
                "realtime_start": "2026-01-15",
                "realtime_end": "2026-02-11",  # closed off, not open-ended anymore
            },
            {
                "series_id": TEST_VINTAGE_ID,
                "date": "2025-12-01",
                "value": "3.15",
                "realtime_start": "2026-02-12",
                "realtime_end": "9999-12-31",
            },
        ]
        load_observations_vintage(engine, second_pull)

        # re-running the *same* second pull must not duplicate rows (idempotent on the
        # (series_id, obs_date, realtime_start) key)
        load_observations_vintage(engine, second_pull)

        stored = read_observations(engine, series_id=TEST_VINTAGE_ID)
        assert len(stored) == 2  # two distinct vintages, not three or four
        assert stored[0]["realtime_end"] == "2026-02-11"  # updated, not left at 9999-12-31
        assert stored[1]["value"] == "3.15"
        assert stored[1]["realtime_end"] == "9999-12-31"
    finally:
        _delete_test_rows(engine, TEST_VINTAGE_ID)


def test_observations_current_upsert_survives_a_day_change(engine):
    """Regression test for a real bug: FRED stamps every row in a non-vintage (current-value)
    pull with realtime_start=realtime_end=today, uniformly. A tomorrow-run pull re-stamps every
    row with a *different* today. Merging on (series_id, obs_date, realtime_start) — like the
    genuinely-vintage-tracked loader does — would treat that as 16,000+ brand-new rows every
    single day instead of an update. load_observations_current merges on (series_id, obs_date)
    alone specifically to avoid this; this test simulates the day change directly."""
    from db_snowflake import init_schema, load_observations_current, read_observations

    init_schema(engine)

    try:
        # "today's" pull
        day_one = [
            {
                "series_id": TEST_CURRENT_ID,
                "date": "2026-08-05",
                "value": "4.50",
                "realtime_start": "2026-08-05",
                "realtime_end": "2026-08-05",
            }
        ]
        load_observations_current(engine, day_one)

        # "tomorrow's" pull: same observation date, unchanged value, but a completely
        # different realtime_start/realtime_end stamp -- exactly what FRED actually sends.
        day_two = [
            {
                "series_id": TEST_CURRENT_ID,
                "date": "2026-08-05",
                "value": "4.50",
                "realtime_start": "2026-08-06",
                "realtime_end": "2026-08-06",
            }
        ]
        load_observations_current(engine, day_two)

        stored = read_observations(engine, series_id=TEST_CURRENT_ID)
        assert len(stored) == 1  # updated in place, not a second row
        assert stored[0]["realtime_start"] == "2026-08-06"
    finally:
        _delete_test_rows(engine, TEST_CURRENT_ID)
