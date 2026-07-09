"""M1 (red-first): ingest returns the expected shape.

Pure parsing is tested against a captured FRED payload; the HTTP call is tested
against a fake session so no network is required.
"""

from ingest.fred import fetch_observations, parse_observations

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
