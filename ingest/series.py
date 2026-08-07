"""The curated FRED series list for the CRE macro-conditions warehouse.

Every ID here was verified against the live FRED `/fred/series` endpoint before being added —
see DECISIONS.md's Phase 2 entry for the verification method and the per-series rationale.
`group` is this project's own classification (FRED has no such concept); it exists so the
Phase 4 `dim_series` seed has a starting point, not because RAW needs it — RAW stores exactly
what FRED/ALFRED return, nothing assigned by us.

`vintage_tracked` controls whether the ingest pulls full ALFRED revision history
(`full_history=True` in ingest.fred.fetch_vintage_observations) or just the current vintage.
False for the daily market-rate series: verified live against FRED that these hit the API's
2000-vintage-date cap (FRED periodically re-stamps their *entire* history under a new
realtime_start even when no value changed — a bulk republish, not a real revision), and even
if that weren't a hard API limit, full revision tracking isn't economically meaningful for a
once-published, essentially-never-revised market rate. See DECISIONS.md's Phase 2 entry.
"""

from __future__ import annotations

SERIES = [
    # Treasury yields across the curve — spread/inversion analysis in the mart. Market-observed,
    # essentially never revised: current value only (still with realtime_start/end preserved).
    {"series_id": "DGS3MO", "group": "treasury_curve", "vintage_tracked": False},
    {"series_id": "DGS1", "group": "treasury_curve", "vintage_tracked": False},
    {"series_id": "DGS2", "group": "treasury_curve", "vintage_tracked": False},
    {"series_id": "DGS5", "group": "treasury_curve", "vintage_tracked": False},
    {"series_id": "DGS10", "group": "treasury_curve", "vintage_tracked": False},
    {"series_id": "DGS30", "group": "treasury_curve", "vintage_tracked": False},
    # Short rate — same reasoning as the Treasury curve.
    {"series_id": "SOFR", "group": "short_rate", "vintage_tracked": False},
    # Inflation — genuinely revised monthly prints; this is the point of tracking vintages.
    {"series_id": "CPIAUCSL", "group": "inflation", "vintage_tracked": True},
    {"series_id": "CPILFESL", "group": "inflation", "vintage_tracked": True},
    # Labor — PAYEMS in particular is revised repeatedly for ~2 years after initial release.
    {"series_id": "UNRATE", "group": "labor", "vintage_tracked": True},
    {"series_id": "PAYEMS", "group": "labor", "vintage_tracked": True},
    # Commercial property prices — revised as more transaction data comes in.
    {"series_id": "COMREPUSQ159N", "group": "property_prices", "vintage_tracked": True},
    # Bank lending standards (SLOOS), split by CRE loan purpose.
    {
        "series_id": "SUBLPDRCSC",
        "group": "credit_conditions",
        "vintage_tracked": True,
    },  # construction & land development
    {
        "series_id": "SUBLPDRCSN",
        "group": "credit_conditions",
        "vintage_tracked": True,
    },  # nonfarm nonresidential
    {
        "series_id": "SUBLPDRCSM",
        "group": "credit_conditions",
        "vintage_tracked": True,
    },  # multifamily
    # CRE loan delinquency, bank balance sheets.
    {
        "series_id": "DRCRELEXFACBS",
        "group": "credit_conditions",
        "vintage_tracked": True,
    },  # all commercial banks
    {
        "series_id": "DRCRELEXFT100S",
        "group": "credit_conditions",
        "vintage_tracked": True,
    },  # top-100 banks by assets
]

SERIES_IDS = [s["series_id"] for s in SERIES]
