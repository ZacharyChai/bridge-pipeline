"""FRED ingest: fetch and parse a macro series from the FRED API.

Kept deliberately thin — HTTP in, list-of-dicts out. All the interesting logic
(cleaning, typing, quality) lives downstream in transform/, so this stays easy
to test with a fake session and no network.
"""

from __future__ import annotations

import requests

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


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
