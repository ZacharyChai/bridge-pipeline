"""Data-quality checks. Each raises DataQualityError on violation.

These are the automated assertions the brief calls for — schema/nulls, row
count, uniqueness, numeric values, and freshness — run on the clean rows before
they're trusted as the warehouse output.
"""

from __future__ import annotations

import datetime as dt


class DataQualityError(Exception):
    """Raised when clean data fails a quality assertion."""


def check_no_null_keys(rows: list[dict]) -> None:
    for row in rows:
        if row.get("series_id") in (None, "") or row.get("date") is None:
            raise DataQualityError(f"null primary-key field in row: {row!r}")


def check_row_count(rows: list[dict], *, min_rows: int, max_rows: int) -> None:
    n = len(rows)
    if not (min_rows <= n <= max_rows):
        raise DataQualityError(f"row count {n} outside expected range [{min_rows}, {max_rows}]")


def check_unique_pk(rows: list[dict]) -> None:
    keys = [(r["series_id"], r["date"]) for r in rows]
    if len(keys) != len(set(keys)):
        dupes = {k for k in keys if keys.count(k) > 1}
        raise DataQualityError(f"duplicate primary keys: {sorted(dupes)}")


def check_values_numeric(rows: list[dict]) -> None:
    for row in rows:
        if not isinstance(row.get("value"), (int, float)) or isinstance(row.get("value"), bool):
            raise DataQualityError(f"non-numeric value in row: {row!r}")


def check_freshness(rows: list[dict], *, max_age_days: int, today: dt.date | None = None) -> None:
    if not rows:
        raise DataQualityError("no rows to check freshness on")
    today = today or dt.date.today()
    latest = max(r["date"] for r in rows)
    age = (today - latest).days
    if age > max_age_days:
        raise DataQualityError(
            f"stale data: latest observation {latest} is {age} days old (max {max_age_days})"
        )


def run_all_checks(
    rows: list[dict],
    *,
    min_rows: int,
    max_rows: int,
    max_age_days: int,
    today: dt.date | None = None,
) -> None:
    """Run every check; raises on the first violation."""
    check_no_null_keys(rows)
    check_values_numeric(rows)
    check_unique_pk(rows)
    check_row_count(rows, min_rows=min_rows, max_rows=max_rows)
    check_freshness(rows, max_age_days=max_age_days, today=today)
