"""M1 integration: prove the full pipeline lands rows in Postgres.

Skipped automatically when no Postgres is reachable, so the unit suite stays
green anywhere (laptop, CI). Runs for real once the warehouse is up (M2),
exercising ingest -> raw table -> transform -> clean table end to end.
"""

import pytest

from config import load_settings
from db import make_engine, ping

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine():
    settings = load_settings()
    eng = make_engine(settings)
    if not ping(eng):
        pytest.skip("no Postgres reachable — set POSTGRES_* env and start the warehouse")
    return eng


def test_pipeline_populates_clean_table(engine):
    from db import init_schema, load_clean, load_raw, read_clean
    from transform.transform import transform

    init_schema(engine)

    raw = [
        {"series_id": "TEST", "date": "2026-07-06", "value": "1.23"},
        {"series_id": "TEST", "date": "2026-07-07", "value": "."},
        {"series_id": "TEST", "date": "2026-07-08", "value": "1.25"},
    ]
    load_raw(engine, raw)
    clean = transform(raw)
    load_clean(engine, clean)

    stored = read_clean(engine, series_id="TEST")
    assert len(stored) == 2  # the "." row is dropped
    assert stored[-1]["value"] == 1.25
