"""Runtime configuration, loaded from environment (and .env for local dev).

One typed Settings object so the rest of the code never reaches into os.environ.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    fred_api_key: str
    fred_series_id: str
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )


def load_settings() -> Settings:
    """Load .env (if present) then read settings from the environment."""
    load_dotenv()
    return Settings(
        fred_api_key=os.environ.get("FRED_API_KEY", ""),
        fred_series_id=os.environ.get("FRED_SERIES_ID", "DGS10"),
        pg_host=os.environ.get("POSTGRES_HOST", "localhost"),
        pg_port=int(os.environ.get("POSTGRES_PORT", "5432")),
        pg_db=os.environ.get("POSTGRES_DB", "bridge"),
        pg_user=os.environ.get("POSTGRES_USER", "bridge"),
        pg_password=os.environ.get("POSTGRES_PASSWORD", ""),
    )


@dataclass(frozen=True)
class SnowflakeSettings:
    """Connection settings for the Phase 2 Snowflake RAW loader. Separate from Settings
    (above) rather than folded in, since the two warehouses are unrelated connections that
    happen to coexist during the Postgres-to-Snowflake migration — see AUDIT.md."""

    fred_api_key: str
    account: str
    user: str
    password: str
    role: str
    warehouse: str
    database: str

    @property
    def database_url(self):
        # Import here, not at module level: snowflake-sqlalchemy is only needed by the
        # Snowflake path, and the legacy Postgres path shouldn't gain a hard dependency on it.
        from snowflake.sqlalchemy import URL

        return URL(
            account=self.account,
            user=self.user,
            password=self.password,
            role=self.role,
            warehouse=self.warehouse,
            database=self.database,
        )


def load_snowflake_settings() -> SnowflakeSettings:
    """Load .env (if present) then read Snowflake settings from the environment.

    Reuses the same SNOWFLAKE_* variables dbt's profiles.yml reads (see dbt/profiles.yml) —
    one set of credentials, two tools connecting to the same account.
    """
    load_dotenv()
    return SnowflakeSettings(
        fred_api_key=os.environ.get("FRED_API_KEY", ""),
        account=os.environ.get("SNOWFLAKE_ACCOUNT", ""),
        user=os.environ.get("SNOWFLAKE_USER", ""),
        password=os.environ.get("SNOWFLAKE_PASSWORD", ""),
        role=os.environ.get("SNOWFLAKE_ROLE", "BRIDGE_DBT_ROLE"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "BRIDGE_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "BRIDGE_DB"),
    )


@dataclass(frozen=True)
class ApiSettings:
    """Read-only connection settings for the api/ service (Phase 9).

    Points at the same DuckDB file dbt builds (see dbt/profiles.yml's duckdb output) --
    reuses DBT_DUCKDB_PATH rather than inventing a second variable for one file, the same
    reasoning load_snowflake_settings() gives for reusing SNOWFLAKE_* vars below. The API
    never queries Snowflake directly: spinning up the trial warehouse per request isn't
    something this project's cost constraints (see CLAUDE.md) can carry, and DuckDB is the
    artifact every clone of this repo already has after `make dbt-build`.
    """

    duckdb_path: str


def load_api_settings() -> ApiSettings:
    """Load .env (if present) then read API settings from the environment."""
    load_dotenv()
    return ApiSettings(
        duckdb_path=os.environ.get("DBT_DUCKDB_PATH", "bridge.duckdb"),
    )
