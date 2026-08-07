{#
    Grain: one row per calendar month. The headline consumption table -- combines the curve,
    inflation, labor, property prices, and lending standards into one wide row per month, plus
    derived measures. Built from fct_observations_latest (today's best-known view of history),
    not fct_observations_point_in_time -- this mart answers "what do we know now", the
    point-in-time capability is a separate, deliberately distinct question (see the
    fct_observations_point_in_time model and DECISIONS.md's Phase 4 entry).

    Starts 2015-01 -- see DECISIONS.md for why. SOFR doesn't exist before 2018-04, so its
    column (and anything derived from it) is legitimately null for the first several years:
    expected, not a data quality bug.
#}

with monthly_last_obs as (

    -- one row per series per month: the value from the latest observation within that month.
    -- For daily series this is a month-end snapshot; for monthly series it's the one reading
    -- that month already has; for quarterly series it's the one reading its own quarter-month
    -- has, leaving the other two months of the quarter with no row yet (filled below).
    select
        s.series_id,
        f.value,
        date_trunc('month', d.date_day) as month_date,
        row_number() over (
            partition by s.series_id, date_trunc('month', d.date_day)
            order by d.date_day desc
        ) as rn
    from {{ ref("fct_observations_latest") }} as f
    inner join {{ ref("dim_series") }} as s on f.series_key = s.series_key
    inner join {{ ref("dim_date") }} as d on f.date_key = d.date_key

),

month_spine as (

    select distinct date_trunc('month', date_day) as month_date
    from {{ ref("dim_date") }}
    where date_day >= date '2015-01-01' and date_day <= current_date

),

pivoted as (

    select
        spine.month_date,

        max(case when obs.series_id = 'DGS3MO' then obs.value end) as treasury_3mo_pct,
        max(case when obs.series_id = 'DGS1' then obs.value end) as treasury_1y_pct,
        max(case when obs.series_id = 'DGS2' then obs.value end) as treasury_2y_pct,
        max(case when obs.series_id = 'DGS5' then obs.value end) as treasury_5y_pct,
        max(case when obs.series_id = 'DGS10' then obs.value end) as treasury_10y_pct,
        max(case when obs.series_id = 'DGS30' then obs.value end) as treasury_30y_pct,
        max(case when obs.series_id = 'SOFR' then obs.value end) as sofr_pct,

        max(case when obs.series_id = 'CPIAUCSL' then obs.value end) as cpi_index,
        max(case when obs.series_id = 'CPILFESL' then obs.value end) as core_cpi_index,

        max(case when obs.series_id = 'UNRATE' then obs.value end) as unemployment_rate_pct,
        max(
            case when obs.series_id = 'PAYEMS' then obs.value end
        ) as nonfarm_payrolls_thousands,

        max(
            case when obs.series_id = 'COMREPUSQ159N' then obs.value end
        ) as cre_price_index_yoy_pct,

        max(
            case when obs.series_id = 'SUBLPDRCSC' then obs.value end
        ) as sloos_cre_construction_tightening_pct,
        max(
            case when obs.series_id = 'SUBLPDRCSN' then obs.value end
        ) as sloos_cre_nonresidential_tightening_pct,
        max(
            case when obs.series_id = 'SUBLPDRCSM' then obs.value end
        ) as sloos_cre_multifamily_tightening_pct,

        max(
            case when obs.series_id = 'DRCRELEXFACBS' then obs.value end
        ) as cre_delinquency_all_banks_pct,
        max(
            case when obs.series_id = 'DRCRELEXFT100S' then obs.value end
        ) as cre_delinquency_top100_banks_pct

    from month_spine as spine
    left join
        monthly_last_obs as obs
        on spine.month_date = obs.month_date and obs.rn = 1
    group by spine.month_date

),

filled as (

    -- forward-fill the quarterly series: carry the last known reading forward into the two
    -- months of each quarter that don't get their own print. Standard treatment for
    -- lower-frequency data in a monthly report -- "last known reading" rather than leaving
    -- gaps a BI tool would otherwise render as a drop to zero.
    select
        month_date,
        treasury_3mo_pct,
        treasury_1y_pct,
        treasury_2y_pct,
        treasury_5y_pct,
        treasury_10y_pct,
        treasury_30y_pct,
        sofr_pct,
        cpi_index,
        core_cpi_index,
        unemployment_rate_pct,
        nonfarm_payrolls_thousands,
        last_value(cre_price_index_yoy_pct ignore nulls) over (
            order by month_date rows between unbounded preceding and current row
        ) as cre_price_index_yoy_pct,
        last_value(sloos_cre_construction_tightening_pct ignore nulls) over (
            order by month_date rows between unbounded preceding and current row
        ) as sloos_cre_construction_tightening_pct,
        last_value(sloos_cre_nonresidential_tightening_pct ignore nulls) over (
            order by month_date rows between unbounded preceding and current row
        ) as sloos_cre_nonresidential_tightening_pct,
        last_value(sloos_cre_multifamily_tightening_pct ignore nulls) over (
            order by month_date rows between unbounded preceding and current row
        ) as sloos_cre_multifamily_tightening_pct,
        last_value(cre_delinquency_all_banks_pct ignore nulls) over (
            order by month_date rows between unbounded preceding and current row
        ) as cre_delinquency_all_banks_pct,
        last_value(cre_delinquency_top100_banks_pct ignore nulls) over (
            order by month_date rows between unbounded preceding and current row
        ) as cre_delinquency_top100_banks_pct
    from pivoted

),

derived as (

    select
        *,
        treasury_10y_pct - treasury_2y_pct as treasury_10y_2y_spread_pct,

        (cpi_index / nullif(lag(cpi_index, 12) over (order by month_date), 0) - 1)
        * 100 as cpi_yoy_pct,
        (core_cpi_index / nullif(lag(core_cpi_index, 12) over (order by month_date), 0) - 1)
        * 100 as core_cpi_yoy_pct,
        unemployment_rate_pct
        - lag(unemployment_rate_pct, 12)
            over (order by month_date)
            as unemployment_rate_yoy_change_pct,
        nonfarm_payrolls_thousands
        - lag(nonfarm_payrolls_thousands, 12)
            over (order by month_date) as nonfarm_payrolls_yoy_change_thousands

    from filled

)

select
    *,
    -- real 10y rate proxy: nominal 10y yield less realized headline CPI inflation. Not a
    -- TIPS-based real yield (no TIPS series in the catalog) -- see DECISIONS.md.
    treasury_10y_pct - cpi_yoy_pct as real_10y_rate_pct,

    -- 60-month (5-year) trailing z-score on the headline spread -- see DECISIONS.md for why
    -- this window and why this measure. Null until 60 months of history accumulate; expected.
    (
        treasury_10y_2y_spread_pct
        - avg(treasury_10y_2y_spread_pct) over (
            order by month_date rows between 59 preceding and current row
        )
    )
    / nullif(
        stddev_samp(treasury_10y_2y_spread_pct) over (
            order by month_date rows between 59 preceding and current row
        ),
        0
    ) as treasury_10y_2y_spread_zscore_60mo

from derived
