{#
    Singular test, Phase 4's acceptance criterion: mart_cre_macro_conditions has no nulls in
    its key measures for the period where source data exists.

    Scoped to a 12-month window ending 2 months before today, not the mart's full 2015+ range
    or a window right up to today:
    - Early months are legitimately null before a series existed (SOFR starts 2018-04) or
      before enough lookback exists for YoY calculations -- expected, not a bug.
    - The most recent ~1-2 months are excluded because monthly government series (CPI,
      unemployment, payrolls) publish with a reporting lag -- e.g. July's CPI isn't released
      until mid-August. Testing right up to "today" would flag perfectly normal not-yet-
      published data as a failure.

    One specific real gap is also excluded explicitly: FRED's own CPIAUCSL/CPILFESL/UNRATE
    carry a genuine "." (missing) marker for 2025-10, which lines up with the documented
    43-day US government shutdown (2025-10-01 to 2025-11-13) that delayed BLS data releases.
    Verified directly against source data, not assumed -- see DECISIONS.md's Phase 4 entry.
    This is exactly the "nulls explained where source data doesn't exist" case the acceptance
    criterion anticipates, not something to route around by loosening the test generally.

    treasury_10y_2y_spread_zscore_60mo is deliberately excluded from this check: it needs 60
    months of trailing history, which the DuckDB seed's ~4-year trimmed fixture never
    accumulates. That's an explained gap on the duckdb target specifically, not a bug -- see
    DECISIONS.md's Phase 4 entry.

    Severity: warn, not error -- deliberately, see DECISIONS.md's Phase 5 entry. A failure here
    is as likely to mean "FRED published late again" (operational, seen for real with the 2025
    shutdown) as "the pipeline actually broke" -- worth a human's attention on every run, not a
    reason to fail the whole build the way a genuine grain or referential-integrity violation
    would.
#}

{{ config(severity="warn") }}

select
    month_date,
    'a key measure was null in the last 12 complete months' as failure_reason
from {{ ref("mart_cre_macro_conditions") }}
where
    month_date >= date_trunc('month', current_date) - interval '13 months'
    and month_date < date_trunc('month', current_date) - interval '1 month'
    and month_date != date '2025-10-01'
    and (
        treasury_3mo_pct is null
        or treasury_1y_pct is null
        or treasury_2y_pct is null
        or treasury_5y_pct is null
        or treasury_10y_pct is null
        or treasury_30y_pct is null
        or sofr_pct is null
        or cpi_index is null
        or core_cpi_index is null
        or unemployment_rate_pct is null
        or nonfarm_payrolls_thousands is null
        or cre_price_index_yoy_pct is null
        or sloos_cre_construction_tightening_pct is null
        or sloos_cre_nonresidential_tightening_pct is null
        or sloos_cre_multifamily_tightening_pct is null
        or cre_delinquency_all_banks_pct is null
        or cre_delinquency_top100_banks_pct is null
        or treasury_10y_2y_spread_pct is null
        or cpi_yoy_pct is null
        or core_cpi_yoy_pct is null
        or unemployment_rate_yoy_change_pct is null
        or nonfarm_payrolls_yoy_change_thousands is null
        or real_10y_rate_pct is null
    )
