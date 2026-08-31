"""FastAPI service (Phase 9): read-only REST endpoints over the dbt marts.

Wraps dim_series, fct_observations_latest, and fct_observations_point_in_time -- the same
warehouse every other part of this project builds, nothing new to maintain in parallel.
Run it with `make api-run` (needs a real bridge.duckdb -- `make dbt-build` first) and see
README.md's API section for example requests. DECISIONS.md's Phase 9 entry has the design
writeup: why this queries DuckDB directly instead of going through SQLAlchemy, and why the
as-of endpoint re-derives the point-in-time ranking instead of querying the dbt view.
"""

from __future__ import annotations

import datetime as dt

import duckdb
from fastapi import Depends, FastAPI, HTTPException, Query

from api.db import get_connection
from api.schemas import Observation, Series

app = FastAPI(
    title="bridge-pipeline API",
    description="Read-only REST API over the bridge-pipeline CRE macro warehouse.",
    version="0.1.0",
)

_SERIES_COLUMNS = (
    "series_id",
    "title",
    "frequency",
    "units",
    "seasonal_adjustment",
    "observation_start_date",
    "observation_end_date",
    "category",
)
_OBSERVATION_COLUMNS = ("series_id", "date", "value", "realtime_start_date", "realtime_end_date")


def _series(row: tuple) -> Series:
    return Series(**dict(zip(_SERIES_COLUMNS, row, strict=True)))


def _observation(row: tuple) -> Observation:
    return Observation(**dict(zip(_OBSERVATION_COLUMNS, row, strict=True)))


def _get_series_or_404(con: duckdb.DuckDBPyConnection, series_id: str) -> Series:
    row = con.execute(
        f"select {', '.join(_SERIES_COLUMNS)} from dim_series where series_id = ?",
        [series_id],
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown series_id: {series_id}")
    return _series(row)


@app.get("/")
def root() -> dict:
    return {
        "name": "bridge-pipeline API",
        "docs": "/docs",
        "endpoints": [
            "/health",
            "/series",
            "/series/{series_id}",
            "/series/{series_id}/observations",
            "/series/{series_id}/observations/as-of",
        ],
    }


@app.get("/health")
def health(con: duckdb.DuckDBPyConnection = Depends(get_connection)) -> dict:
    con.execute("select 1")
    return {"status": "ok"}


@app.get("/series", response_model=list[Series])
def list_series(
    category: str | None = Query(default=None, description="Filter by dim_series.category"),
    con: duckdb.DuckDBPyConnection = Depends(get_connection),
) -> list[Series]:
    rows = con.execute(
        f"""
        select {", ".join(_SERIES_COLUMNS)}
        from dim_series
        where (? is null or category = ?)
        order by series_id
        """,
        [category, category],
    ).fetchall()
    return [_series(row) for row in rows]


@app.get("/series/{series_id}", response_model=Series)
def get_series(series_id: str, con: duckdb.DuckDBPyConnection = Depends(get_connection)) -> Series:
    return _get_series_or_404(con, series_id)


@app.get("/series/{series_id}/observations", response_model=list[Observation])
def get_observations(
    series_id: str,
    start_date: dt.date | None = Query(default=None),
    end_date: dt.date | None = Query(default=None),
    con: duckdb.DuckDBPyConnection = Depends(get_connection),
) -> list[Observation]:
    """The warehouse's best-known value for each (series, date) as of right now -- reads
    fct_observations_latest, the mart that already picks the newest vintage per row."""
    _get_series_or_404(con, series_id)
    rows = con.execute(
        """
        select s.series_id, d.date_day as date, o.value,
               o.realtime_start_date, o.realtime_end_date
        from fct_observations_latest o
        join dim_series s on s.series_key = o.series_key
        join dim_date d on d.date_key = o.date_key
        where s.series_id = ?
          and (cast(? as date) is null or d.date_day >= cast(? as date))
          and (cast(? as date) is null or d.date_day <= cast(? as date))
        order by d.date_day
        """,
        [series_id, start_date, start_date, end_date, end_date],
    ).fetchall()
    return [_observation(row) for row in rows]


@app.get("/series/{series_id}/observations/as-of", response_model=list[Observation])
def get_observations_as_of(
    series_id: str,
    as_of_date: dt.date = Query(
        ..., description="Reconstruct the series as it was known on this date"
    ),
    start_date: dt.date | None = Query(default=None),
    end_date: dt.date | None = Query(default=None),
    con: duckdb.DuckDBPyConnection = Depends(get_connection),
) -> list[Observation]:
    """Point-in-time lookup: what this series looked like as of as_of_date.

    Re-derives dbt/models/marts/fct_observations_point_in_time.sql's ranking logic against
    fct_observations directly, with as_of_date substituted for that model's current_date
    default. The dbt view itself always answers "as of right now" (current_date is a
    runtime SQL function baked into the compiled view, not the compile-time as_of_date dbt
    var), so an arbitrary historical as_of_date has to go through fct_observations, the one
    table that still carries every vintage. See DECISIONS.md's Phase 9 entry.
    """
    _get_series_or_404(con, series_id)
    rows = con.execute(
        """
        with base as (
            select f.series_key, f.date_key, f.realtime_start_date, f.realtime_end_date,
                   f.value, s.series_id
            from fct_observations f
            join dim_series s on s.series_key = f.series_key
            where s.series_id = ?
        ),
        filtered as (
            select * from base where realtime_start_date <= ?
        ),
        ranked as (
            select *,
                   row_number() over (
                       partition by series_key, date_key order by realtime_start_date desc
                   ) as rn
            from filtered
        )
        select r.series_id, d.date_day as date, r.value,
               r.realtime_start_date, r.realtime_end_date
        from ranked r
        join dim_date d on d.date_key = r.date_key
        where r.rn = 1
          and (cast(? as date) is null or d.date_day >= cast(? as date))
          and (cast(? as date) is null or d.date_day <= cast(? as date))
        order by d.date_day
        """,
        [series_id, as_of_date, start_date, start_date, end_date, end_date],
    ).fetchall()
    return [_observation(row) for row in rows]
