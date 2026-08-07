{#
    Range covers the earliest series (PAYEMS, observation_start 1939-01-01) through a few years
    of headroom past today, so the spine never needs regenerating as new observations land.
    No fiscal-year convention was specified for this domain, so fiscal_year/fiscal_quarter are
    plain aliases of the calendar year/quarter -- see DECISIONS.md's Phase 4 entry.
#}

with spine as (

    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('1939-01-01' as date)",
        end_date="cast('2031-01-01' as date)"
    ) }}

),

calendared as (

    select
        cast(date_day as date) as date_day,
        extract(year from date_day) as year,
        extract(quarter from date_day) as quarter,
        extract(month from date_day) as month,
        extract(day from date_day) as day,
        extract(dow from date_day) as day_of_week,
        extract(year from date_day) as fiscal_year,
        extract(quarter from date_day) as fiscal_quarter,
        (date_day = last_day(date_day)) as is_month_end,
        (
            date_day = last_day(date_day) and extract(month from date_day) in (3, 6, 9, 12)
        ) as is_quarter_end,
        (extract(dow from date_day) not in (0, 6)) as is_business_day

    from spine

)

select
    {{ dbt_utils.generate_surrogate_key(["date_day"]) }} as date_key,
    *
from calendared
