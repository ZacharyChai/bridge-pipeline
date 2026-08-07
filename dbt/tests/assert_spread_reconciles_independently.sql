{#
    Singular test, Phase 5: mart_cre_macro_conditions.treasury_10y_2y_spread_pct reconciles
    against an independently calculated value.

    "Independent" means recomputed straight from fct_observations_latest -- the vintage-grain
    fact -- not from the mart's own already-pivoted columns. Re-checking against the mart's own
    treasury_10y_pct/treasury_2y_pct columns would only prove subtraction works; recomputing
    from the base fact also exercises the mart's join/pivot/month-snapshot logic a second,
    differently-shaped way. A non-empty result means the mart's spread doesn't match what the
    base fact independently supports, for that month.
#}

with monthly_last as (

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
    where s.series_id in ('DGS10', 'DGS2')

),

independent as (

    select
        month_date,
        max(case when series_id = 'DGS10' then value end) as dgs10,
        max(case when series_id = 'DGS2' then value end) as dgs2

    from monthly_last
    where rn = 1
    group by month_date

),

compared as (

    select
        m.month_date,
        m.treasury_10y_2y_spread_pct as mart_spread,
        i.dgs10 - i.dgs2 as independent_spread

    from {{ ref("mart_cre_macro_conditions") }} as m
    inner join independent as i on m.month_date = i.month_date

)

select
    month_date,
    mart_spread,
    independent_spread
from compared
where
    abs(coalesce(mart_spread, 0) - coalesce(independent_spread, 0)) > 0.0001
    or (mart_spread is null) != (independent_spread is null)
