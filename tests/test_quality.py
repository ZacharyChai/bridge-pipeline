"""M1 (red-first): data-quality checks.

The brief's required checks: no nulls in keys, row count in an expected range,
no duplicate primary keys, values are numeric, and data is fresh. Each check
raises DataQualityError on violation; run_all_checks runs them together.
"""

import datetime as dt

import pytest

from transform.quality import (
    DataQualityError,
    check_freshness,
    check_no_null_keys,
    check_row_count,
    check_unique_pk,
    check_values_numeric,
    run_all_checks,
)

TODAY = dt.date(2026, 7, 9)

GOOD = [
    {"series_id": "DGS10", "date": dt.date(2026, 7, 6), "value": 4.48},
    {"series_id": "DGS10", "date": dt.date(2026, 7, 7), "value": 4.55},
]


def test_good_data_passes_all():
    # should not raise
    run_all_checks(GOOD, min_rows=1, max_rows=100, max_age_days=7, today=TODAY)


def test_null_key_raises():
    bad = GOOD + [{"series_id": "DGS10", "date": None, "value": 4.5}]
    with pytest.raises(DataQualityError):
        check_no_null_keys(bad)


def test_duplicate_pk_raises():
    bad = GOOD + [{"series_id": "DGS10", "date": dt.date(2026, 7, 7), "value": 4.55}]
    with pytest.raises(DataQualityError):
        check_unique_pk(bad)


def test_row_count_out_of_range_raises():
    with pytest.raises(DataQualityError):
        check_row_count(GOOD, min_rows=10, max_rows=100)
    with pytest.raises(DataQualityError):
        check_row_count(GOOD, min_rows=1, max_rows=1)


def test_non_numeric_value_raises():
    bad = GOOD + [{"series_id": "DGS10", "date": dt.date(2026, 7, 8), "value": "."}]
    with pytest.raises(DataQualityError):
        check_values_numeric(bad)


def test_stale_data_raises():
    stale = [{"series_id": "DGS10", "date": dt.date(2026, 6, 1), "value": 4.2}]
    with pytest.raises(DataQualityError):
        check_freshness(stale, max_age_days=7, today=TODAY)


def test_fresh_data_passes():
    # latest date within the window -> no raise
    check_freshness(GOOD, max_age_days=7, today=TODAY)
