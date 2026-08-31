"""Read-only DuckDB access for the API.

One connection per request rather than a pool -- this is a small, single-file embedded
warehouse queried read-only, and a pool is complexity this project doesn't need to defend
in an interview (see DECISIONS.md's Phase 9 entry). DuckDB allows multiple concurrent
read_only connections against the same file, so this is safe alongside a `dbt build` writer
as long as no writer is active at the instant a request lands -- a fine guarantee for a
portfolio service, not a claim this would hold under real concurrent-write traffic.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import duckdb

from config import ApiSettings, load_api_settings


def get_connection_for(settings: ApiSettings) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(settings.duckdb_path, read_only=True)


def ping(settings: ApiSettings) -> bool:
    """True if the DuckDB file exists and opens read-only.

    Mirrors db.py's ping() and db_snowflake.py's ping() -- same shape, so integration tests
    can skip gracefully the same way when no build is present (see tests/test_api.py).
    """
    if not Path(settings.duckdb_path).exists():
        return False
    try:
        con = get_connection_for(settings)
        con.execute("select 1")
        con.close()
        return True
    except duckdb.Error:
        return False


def get_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    """FastAPI dependency: yields a request-scoped read-only connection, always closed."""
    settings = load_api_settings()
    con = get_connection_for(settings)
    try:
        yield con
    finally:
        con.close()
