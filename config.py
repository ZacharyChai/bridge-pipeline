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
