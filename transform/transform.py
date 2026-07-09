"""Transform raw FRED rows into clean, typed, deduplicated observations.

Pure function: no I/O, no globals. Raw string rows in, typed rows out. This is
where the data-fluency shows — the rules for what counts as a valid observation.
"""

from __future__ import annotations

import datetime as dt

# FRED encodes "no observation on this day" (weekends, holidays) as ".".
MISSING_MARKERS = {".", "", None}


def _parse_date(value: str | dt.date) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def transform(raw_rows: list[dict]) -> list[dict]:
    """Clean raw observations into warehouse-ready rows.

    - drops missing values (FRED's "." marker, empty, or null)
    - coerces value to float and date to datetime.date
    - de-duplicates on the (series_id, date) primary key (last write wins)
    - returns rows sorted chronologically
    """
    by_key: dict[tuple[str, dt.date], dict] = {}
    for row in raw_rows:
        value = row.get("value")
        if value in MISSING_MARKERS:
            continue
        date = _parse_date(row["date"])
        clean = {
            "series_id": row["series_id"],
            "date": date,
            "value": float(value),
        }
        by_key[(clean["series_id"], date)] = clean

    return sorted(by_key.values(), key=lambda r: (r["series_id"], r["date"]))
