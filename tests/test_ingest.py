"""M1 (red-first): ingest returns the expected shape.

Pure parsing is tested against a captured FRED payload; the HTTP call is tested
against a fake session so no network is required.

Phase 2 adds: vintage-aware parsing/fetching (preserves realtime_start/realtime_end
instead of discarding them), series metadata parsing/fetching, and API-failure
propagation (a real gap the Phase 0 audit flagged — nothing exercised this before).
"""

import pytest
import requests

from ingest.fred import (
    ALFRED_ALL_VINTAGES_END,
    ALFRED_ALL_VINTAGES_START,
    fetch_observations,
    fetch_series_metadata,
    fetch_vintage_observations,
    parse_observations,
    parse_series_metadata,
    parse_vintage_observations,
)

# A trimmed but real-shaped FRED /series/observations payload. Note the "."
# value — FRED's missing-data marker for non-trading days. Handling it is the
# whole point of the transform/quality layer.
SAMPLE_PAYLOAD = {
    "observation_start": "1600-01-01",
    "observation_end": "9999-12-31",
    "count": 4,
    "observations": [
        {
            "realtime_start": "2026-07-08",
            "realtime_end": "2026-07-08",
            "date": "2026-07-01",
            "value": "4.40",
        },
        {
            "realtime_start": "2026-07-08",
            "realtime_end": "2026-07-08",
            "date": "2026-07-02",
            "value": "4.43",
        },
        {
            "realtime_start": "2026-07-08",
            "realtime_end": "2026-07-08",
            "date": "2026-07-03",
            "value": ".",
        },
        {
            "realtime_start": "2026-07-08",
            "realtime_end": "2026-07-08",
            "date": "2026-07-06",
            "value": "4.48",
        },
    ],
}


def test_parse_observations_shape():
    rows = parse_observations(SAMPLE_PAYLOAD, series_id="DGS10")
    assert len(rows) == 4
    for row in rows:
        assert set(row.keys()) == {"series_id", "date", "value"}
        assert row["series_id"] == "DGS10"
    # raw values are preserved verbatim, including the missing-data marker
    assert rows[0]["date"] == "2026-07-01"
    assert rows[0]["value"] == "4.40"
    assert rows[2]["value"] == "."


def test_parse_observations_empty():
    assert parse_observations({"observations": []}, series_id="DGS10") == []


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _FakeSession:
    """Records the request and returns a canned payload — no network."""

    def __init__(self, payload):
        self._payload = payload
        self.last_url = None
        self.last_params = None

    def get(self, url, params=None, timeout=None):
        self.last_url = url
        self.last_params = params
        return _FakeResponse(self._payload)


def test_fetch_observations_builds_request_and_parses():
    session = _FakeSession(SAMPLE_PAYLOAD)
    rows = fetch_observations("DGS10", api_key="secret", session=session)

    # request was built correctly
    assert session.last_params["series_id"] == "DGS10"
    assert session.last_params["api_key"] == "secret"
    assert session.last_params["file_type"] == "json"
    # and the response was parsed into the expected shape
    assert len(rows) == 4
    assert rows[3]["value"] == "4.48"


class _FailingResponse:
    """Simulates a FRED API error response: raise_for_status raises before .json()
    is ever reached, matching real `requests` behavior."""

    def raise_for_status(self):
        raise requests.HTTPError("500 Server Error: FRED is having a bad day")

    def json(self):
        raise AssertionError(".json() must not be called once raise_for_status() has raised")


class _FailingSession:
    def get(self, url, params=None, timeout=None):
        return _FailingResponse()


def test_fetch_observations_raises_on_http_error():
    with pytest.raises(requests.HTTPError):
        fetch_observations("DGS10", api_key="secret", session=_FailingSession())


# --- Phase 2: vintage-aware observations (ALFRED) ---------------------------------

# Two rows for the *same* observation date: an initial print, then a later revision.
# This is exactly what a real ALFRED pull looks like for a series that gets revised —
# e.g. CPI or payrolls — and it's what parse_observations (above) collapses away by
# only ever keeping series_id/date/value.
SAMPLE_VINTAGE_PAYLOAD = {
    "observations": [
        {
            "realtime_start": "2026-01-15",
            "realtime_end": "2026-02-11",
            "date": "2025-12-01",
            "value": "3.10",
        },
        {
            "realtime_start": "2026-02-12",
            "realtime_end": "9999-12-31",
            "date": "2025-12-01",
            "value": "3.15",
        },
    ]
}


def test_parse_vintage_observations_preserves_revision_history():
    rows = parse_vintage_observations(SAMPLE_VINTAGE_PAYLOAD, series_id="CPIAUCSL")
    assert len(rows) == 2  # both vintages kept, not collapsed to one row per date
    for row in rows:
        assert set(row.keys()) == {"series_id", "date", "value", "realtime_start", "realtime_end"}
        assert row["date"] == "2025-12-01"
    assert rows[0]["value"] == "3.10"
    assert rows[0]["realtime_end"] == "2026-02-11"
    assert rows[1]["value"] == "3.15"
    assert rows[1]["realtime_end"] == "9999-12-31"  # current vintage, still open


def test_fetch_vintage_observations_requests_full_revision_history():
    session = _FakeSession(SAMPLE_VINTAGE_PAYLOAD)
    rows = fetch_vintage_observations("CPIAUCSL", api_key="secret", session=session)

    # the wide realtime window is what turns a plain FRED pull into an ALFRED pull
    assert session.last_params["realtime_start"] == ALFRED_ALL_VINTAGES_START
    assert session.last_params["realtime_end"] == ALFRED_ALL_VINTAGES_END
    assert len(rows) == 2


def test_fetch_vintage_observations_raises_on_http_error():
    with pytest.raises(requests.HTTPError):
        fetch_vintage_observations("CPIAUCSL", api_key="secret", session=_FailingSession())


def test_fetch_vintage_observations_full_history_false_omits_wide_window():
    # full_history=False is for series where full ALFRED history either isn't fetchable in
    # one call or isn't meaningful (see ingest/series.py's vintage_tracked flag) — it should
    # fall back to FRED's own default window rather than requesting everything, while still
    # preserving realtime_start/realtime_end (unlike the legacy parse_observations).
    session = _FakeSession(SAMPLE_VINTAGE_PAYLOAD)
    rows = fetch_vintage_observations(
        "DGS10", api_key="secret", session=session, full_history=False
    )

    assert "realtime_start" not in session.last_params
    assert "realtime_end" not in session.last_params
    assert len(rows) == 2
    assert set(rows[0].keys()) == {"series_id", "date", "value", "realtime_start", "realtime_end"}


# --- Phase 2: series metadata -------------------------------------------------------

SAMPLE_SERIES_PAYLOAD = {
    "seriess": [
        {
            "id": "CPIAUCSL",
            "title": "Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
            "frequency_short": "M",
            "units_short": "Index 1982-1984=100",
            "seasonal_adjustment_short": "SA",
            "observation_start": "1947-01-01",
            "observation_end": "2026-06-01",
        }
    ]
}


def test_parse_series_metadata_shape():
    meta = parse_series_metadata(SAMPLE_SERIES_PAYLOAD, series_id="CPIAUCSL")
    assert meta == {
        "series_id": "CPIAUCSL",
        "title": "Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
        "frequency": "M",
        "units": "Index 1982-1984=100",
        "seasonal_adjustment": "SA",
        "observation_start": "1947-01-01",
        "observation_end": "2026-06-01",
    }


def test_fetch_series_metadata_builds_request_and_parses():
    session = _FakeSession(SAMPLE_SERIES_PAYLOAD)
    meta = fetch_series_metadata("CPIAUCSL", api_key="secret", session=session)

    assert session.last_params["series_id"] == "CPIAUCSL"
    assert session.last_params["api_key"] == "secret"
    assert meta["series_id"] == "CPIAUCSL"
    assert meta["frequency"] == "M"


def test_fetch_series_metadata_raises_on_http_error():
    with pytest.raises(requests.HTTPError):
        fetch_series_metadata("CPIAUCSL", api_key="secret", session=_FailingSession())
