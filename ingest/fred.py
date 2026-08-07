"""FRED ingest: fetch and parse a macro series from the FRED API.

Kept deliberately thin — HTTP in, list-of-dicts out. All the interesting logic
(cleaning, typing, quality) lives downstream in transform/, so this stays easy
to test with a fake session and no network.

Two ingest shapes live here:
  - fetch_observations / parse_observations — the original M1 path: current values only,
    realtime_start/realtime_end discarded. Still used by the legacy single-series Postgres
    pipeline (ingest/pipeline.py) until that path is retired.
  - fetch_vintage_observations / fetch_series_metadata — the Phase 2 path: full ALFRED
    revision history (every realtime_start/realtime_end preserved) plus series metadata,
    used by the multi-series Snowflake RAW pipeline (ingest/pipeline_snowflake.py).
"""

from __future__ import annotations

import requests

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES_META_URL = "https://api.stlouisfed.org/fred/series"

# FRED's own convention for "give me every vintage that ever existed": a realtime window wide
# enough to cover the full revision history, rather than just the latest value as of today.
# Passing this pair of params to the *same* /series/observations endpoint is what ALFRED's
# vintage behavior actually is — there is no separate ALFRED base URL.
ALFRED_ALL_VINTAGES_START = "1776-07-04"
ALFRED_ALL_VINTAGES_END = "9999-12-31"


def parse_observations(payload: dict, series_id: str) -> list[dict]:
    """Extract raw observations from a FRED JSON payload.

    Values are preserved verbatim (including FRED's "." missing marker); typing
    and cleaning happen in the transform step, not here.
    """
    rows = []
    for obs in payload.get("observations", []):
        rows.append(
            {
                "series_id": series_id,
                "date": obs["date"],
                "value": obs["value"],
            }
        )
    return rows


def fetch_observations(
    series_id: str,
    api_key: str,
    *,
    base_url: str = FRED_BASE,
    session: requests.Session | None = None,
    timeout: int = 30,
    **extra_params: str,
) -> list[dict]:
    """Fetch observations for `series_id` and return them parsed.

    `session` is injectable so tests can supply a fake; extra params (e.g.
    sort_order, limit, observation_start) are passed straight through to FRED.
    """
    session = session or requests.Session()
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        **extra_params,
    }
    resp = session.get(base_url, params=params, timeout=timeout)
    resp.raise_for_status()
    return parse_observations(resp.json(), series_id)


def parse_vintage_observations(payload: dict, series_id: str) -> list[dict]:
    """Extract vintage-aware observations: every revision, with realtime_start/realtime_end
    preserved on each row. Unlike parse_observations, nothing here is discarded."""
    rows = []
    for obs in payload.get("observations", []):
        rows.append(
            {
                "series_id": series_id,
                "date": obs["date"],
                "value": obs["value"],
                "realtime_start": obs["realtime_start"],
                "realtime_end": obs["realtime_end"],
            }
        )
    return rows


def fetch_vintage_observations(
    series_id: str,
    api_key: str,
    *,
    full_history: bool = True,
    base_url: str = FRED_BASE,
    session: requests.Session | None = None,
    timeout: int = 30,
    **extra_params: str,
) -> list[dict]:
    """Fetch observations for `series_id` with realtime_start/realtime_end preserved on
    every row (unlike fetch_observations, which discards them).

    `full_history=True` (default) requests FRED's full revision history via a maximally wide
    realtime window — every vintage FRED has ever published for each observation date. This is
    what makes the pull an ALFRED pull rather than a plain FRED pull.

    `full_history=False` fetches just the current vintage per date (FRED's default window),
    still with realtime_start/realtime_end preserved. Use this for series where full history
    either isn't meaningful or isn't fetchable in one call — see ingest/series.py's
    `vintage_tracked` flag and DECISIONS.md's Phase 2 entry: FRED periodically re-stamps an
    entire daily series' whole history under a new realtime_start even when no value actually
    changed (a bulk republish, not a real revision), which for a series like DGS10 produces
    5000+ "vintage dates" and exceeds FRED's own 2000-vintage-date cap on a single request —
    for essentially never-revised market rates, that's noise, not signal worth chasing.
    """
    session = session or requests.Session()
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        **extra_params,
    }
    if full_history:
        params["realtime_start"] = ALFRED_ALL_VINTAGES_START
        params["realtime_end"] = ALFRED_ALL_VINTAGES_END
    resp = session.get(base_url, params=params, timeout=timeout)
    resp.raise_for_status()
    return parse_vintage_observations(resp.json(), series_id)


def parse_series_metadata(payload: dict, series_id: str) -> dict:
    """Extract the one series record from a FRED /fred/series response."""
    s = payload["seriess"][0]
    return {
        "series_id": series_id,
        "title": s["title"],
        "frequency": s["frequency_short"],
        "units": s["units_short"],
        "seasonal_adjustment": s["seasonal_adjustment_short"],
        "observation_start": s["observation_start"],
        "observation_end": s["observation_end"],
    }


def fetch_series_metadata(
    series_id: str,
    api_key: str,
    *,
    base_url: str = FRED_SERIES_META_URL,
    session: requests.Session | None = None,
    timeout: int = 30,
) -> dict:
    """Fetch a series' own metadata (title, frequency, units, ...), not its observations."""
    session = session or requests.Session()
    params = {"series_id": series_id, "api_key": api_key, "file_type": "json"}
    resp = session.get(base_url, params=params, timeout=timeout)
    resp.raise_for_status()
    return parse_series_metadata(resp.json(), series_id)
