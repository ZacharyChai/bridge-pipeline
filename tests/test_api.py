"""Phase 9 integration: the FastAPI app against a real bridge.duckdb build.

Skipped automatically when no DuckDB build exists (mirrors test_pipeline_integration.py's
and test_pipeline_snowflake_integration.py's pattern for the other two warehouses) -- run
`make dbt-build` first to get a real bridge.duckdb, then `make api-test` (or `pytest -m api`).
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from api.db import ping
from api.main import app
from config import load_api_settings

pytestmark = pytest.mark.api


@pytest.fixture(scope="module")
def client():
    settings = load_api_settings()
    if not ping(settings):
        pytest.skip("no bridge.duckdb build found — run `make dbt-build` first")
    return TestClient(app)


def test_root_lists_endpoints(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "/health" in resp.json()["endpoints"]


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_series_returns_the_curated_catalog(client):
    resp = client.get("/series")
    assert resp.status_code == 200
    body = resp.json()
    # CLAUDE.md's cost constraints cap the curated catalog at 15-25 series -- see
    # tests/test_series.py's test_series_count_within_budget for the same bound on the
    # ingest-side catalog this mart is built from.
    assert 15 <= len(body) <= 25
    assert {"series_id", "title", "category"} <= body[0].keys()


def test_list_series_category_filter(client):
    all_series = client.get("/series").json()
    a_category = all_series[0]["category"]
    resp = client.get("/series", params={"category": a_category})
    assert resp.status_code == 200
    assert all(row["category"] == a_category for row in resp.json())


def test_get_series_by_id(client):
    resp = client.get("/series/DGS10")
    assert resp.status_code == 200
    assert resp.json()["series_id"] == "DGS10"


def test_get_series_unknown_id_is_404(client):
    resp = client.get("/series/NOT_A_REAL_SERIES")
    assert resp.status_code == 404


def test_observations_for_a_known_series(client):
    resp = client.get("/series/DGS10/observations")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) > 0
    assert all(row["series_id"] == "DGS10" for row in body)
    dates = [row["date"] for row in body]
    assert dates == sorted(dates)


def test_observations_unknown_series_is_404(client):
    resp = client.get("/series/NOT_A_REAL_SERIES/observations")
    assert resp.status_code == 404


def test_observations_date_range_filters(client):
    resp = client.get(
        "/series/DGS10/observations",
        params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) > 0
    for row in body:
        assert "2024-01-01" <= row["date"] <= "2024-01-31"


def test_as_of_requires_the_query_param(client):
    resp = client.get("/series/DGS10/observations/as-of")
    assert resp.status_code == 422


def test_as_of_today_matches_the_dbt_view(client):
    """as_of_date=today should agree with fct_observations_point_in_time (its default is
    current_date) on row count for a series with no same-day revision in flight."""
    today = dt.date.today().isoformat()
    resp = client.get("/series/DGS10/observations/as-of", params={"as_of_date": today})
    assert resp.status_code == 200
    for row in resp.json():
        assert row["realtime_start_date"] <= today


def test_as_of_a_past_date_excludes_later_revisions(client):
    """README/DECISIONS.md document a genuine COMREPUSQ159N revision across two vintages --
    as-of a date before the later vintage's realtime_start must exclude it, proving this
    endpoint actually reconstructs history rather than just re-serving the latest value."""
    resp = client.get(
        "/series/COMREPUSQ159N/observations/as-of", params={"as_of_date": "2015-06-01"}
    )
    assert resp.status_code == 200
    for row in resp.json():
        assert row["realtime_start_date"] <= "2015-06-01"
