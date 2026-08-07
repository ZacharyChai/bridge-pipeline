"""Phase 2: sanity checks on the curated FRED series catalog.

Not testing FRED itself (that happened once, live, while curating the list — see
DECISIONS.md) — just guarding against catalog mistakes: duplicates, an empty group,
or drifting outside the 15-25 series budget CLAUDE.md sets.
"""

from ingest.series import SERIES, SERIES_IDS

EXPECTED_GROUPS = {
    "treasury_curve",
    "short_rate",
    "inflation",
    "labor",
    "property_prices",
    "credit_conditions",
}


def test_series_count_within_budget():
    assert 15 <= len(SERIES) <= 25


def test_series_ids_are_unique():
    assert len(SERIES_IDS) == len(set(SERIES_IDS))


def test_every_series_has_a_known_group():
    for s in SERIES:
        assert s["group"] in EXPECTED_GROUPS, f"unrecognized group for {s['series_id']}"


def test_every_group_is_represented():
    groups_present = {s["group"] for s in SERIES}
    assert groups_present == EXPECTED_GROUPS


def test_every_series_declares_vintage_tracked():
    for s in SERIES:
        assert isinstance(s["vintage_tracked"], bool), f"missing/bad flag for {s['series_id']}"


def test_daily_market_rate_series_are_not_vintage_tracked():
    # Verified live against FRED (see DECISIONS.md): these hit the API's 2000-vintage-date
    # cap because FRED periodically re-stamps their entire history under a new realtime_start
    # even when no value changed. Full history isn't fetchable in one call for these, and
    # isn't economically meaningful for a once-published, essentially-never-revised rate.
    never_revised_groups = {"treasury_curve", "short_rate"}
    for s in SERIES:
        if s["group"] in never_revised_groups:
            assert s["vintage_tracked"] is False, f"{s['series_id']} should not be vintage_tracked"
