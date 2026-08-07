{#
    Singular test, Phase 4's required proof: a point-in-time query for an arbitrary past date
    must return the value as it was published at that date, not today's fully-revised figure.

    Real example, not synthetic: COMREPUSQ159N's 2022-07-01 observation (Commercial Real Estate
    Prices) was revised repeatedly as more transaction data came in -- see DECISIONS.md's Phase
    2 entry on why this series has an unusually high revision ratio. Two genuinely different
    values were the "current" figure at two different points in its revision history:
      - as of 2023-09-01: 2.5784 (vintage active 2023-08-01 through 2023-10-31)
      - as of 2024-06-01: 3.1232 (vintage active 2024-05-01 through 2024-07-31)
    If fct_observations' point-in-time logic were wrong -- e.g. collapsed to latest-only, or
    picked the wrong vintage boundary -- these two queries would return the same (wrong) value,
    or no value at all. A non-empty result here means that happened.
#}

with series as (

    select series_key from {{ ref("dim_series") }}
    where series_id = 'COMREPUSQ159N'

),

target_date as (

    select date_key from {{ ref("dim_date") }}
    where date_day = date '2022-07-01'

),

as_of_2023_09 as (

    select f.value
    from {{ ref("fct_observations") }} as f
    inner join series as s on f.series_key = s.series_key
    inner join target_date as t on f.date_key = t.date_key
    where f.realtime_start_date <= date '2023-09-01'
    qualify row_number() over (order by f.realtime_start_date desc) = 1

),

as_of_2024_06 as (

    select f.value
    from {{ ref("fct_observations") }} as f
    inner join series as s on f.series_key = s.series_key
    inner join target_date as t on f.date_key = t.date_key
    where f.realtime_start_date <= date '2024-06-01'
    qualify row_number() over (order by f.realtime_start_date desc) = 1

)

select 'no row as of 2023-09-01 -- point-in-time query found nothing' as failure_reason
where not exists (select 1 from as_of_2023_09)

union all

select 'no row as of 2024-06-01 -- point-in-time query found nothing' as failure_reason
where not exists (select 1 from as_of_2024_06)

union all

select 'wrong value as of 2023-09-01 -- expected 2.5784' as failure_reason
from as_of_2023_09
where round(value, 4) != 2.5784

union all

select 'wrong value as of 2024-06-01 -- expected 3.1232' as failure_reason
from as_of_2024_06
where round(value, 4) != 3.1232

union all

select
    'the two as-of dates returned the same value -- point-in-time isn''t distinguishing vintages'
        as failure_reason
from as_of_2023_09, as_of_2024_06
where round(as_of_2023_09.value, 4) = round(as_of_2024_06.value, 4)
