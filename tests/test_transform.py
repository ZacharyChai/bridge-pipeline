"""M1 (red-first): transform produces the expected clean rows.

transform() is pure: raw string rows in, typed clean rows out. It drops FRED's
"." missing markers, coerces values to float, parses dates, de-duplicates on the
(series_id, date) primary key, and sorts chronologically.
"""

import datetime as dt

from transform.transform import transform

RAW = [
    {"series_id": "DGS10", "date": "2026-07-02", "value": "4.43"},
    {"series_id": "DGS10", "date": "2026-07-01", "value": "4.40"},
    {"series_id": "DGS10", "date": "2026-07-03", "value": "."},  # missing -> dropped
    {"series_id": "DGS10", "date": "2026-07-06", "value": "4.48"},
    {"series_id": "DGS10", "date": "2026-07-06", "value": "4.48"},  # dup PK -> collapsed
    {"series_id": "DGS10", "date": "2026-07-07", "value": None},  # null -> dropped
]


def test_transform_drops_missing_and_nulls():
    clean = transform(RAW)
    values = [r["value"] for r in clean]
    assert None not in values
    assert all(isinstance(v, float) for v in values)
    # 4 non-missing raw rows, two of which share a PK (2026-07-06) -> 3 unique rows
    assert len(clean) == 3


def test_transform_types_and_sort():
    clean = transform(RAW)
    dates = [r["date"] for r in clean]
    assert all(isinstance(d, dt.date) for d in dates)
    assert dates == sorted(dates)  # chronological
    first = clean[0]
    assert first["date"] == dt.date(2026, 7, 1)
    assert first["value"] == 4.40
    assert first["series_id"] == "DGS10"


def test_transform_dedupes_primary_key():
    clean = transform(RAW)
    keys = [(r["series_id"], r["date"]) for r in clean]
    assert len(keys) == len(set(keys))


def test_transform_empty_input():
    assert transform([]) == []
