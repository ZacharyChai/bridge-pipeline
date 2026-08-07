{#
    Grain: one row per series, per observation date, as known on a given as-of date. The as-of
    date is a dbt var (`as_of_date`), defaulting to today when not supplied -- build with
    `dbt build --select fct_observations_point_in_time --vars '{as_of_date: 2023-06-01}'` to see
    what was known as of an arbitrary past date. A view, not a table: the whole point is that
    its answer depends on which as_of_date it's built with, so caching one run's result as a
    table would silently go stale the moment someone asks about a different date.

    For each (series_key, date_key), takes the vintage with the greatest realtime_start_date
    that is still <= as_of_date -- since vintages are contiguous (one ends exactly where the
    next begins), that's always the vintage that was actually active on that date. No need to
    also check realtime_end_date.
#}

{{ config(materialized="view") }}

{% set as_of_date_var = var("as_of_date", none) %}

with base as (

    select * from {{ ref("fct_observations") }}

),

filtered as (

    select *
    from base
    where
        realtime_start_date
        <= {% if as_of_date_var %} cast('{{ as_of_date_var }}' as date)
        {%- else %} current_date
    {%- endif %}

),

ranked as (

    select
        *,
        row_number() over (
            partition by series_key, date_key order by realtime_start_date desc
        ) as rn

    from filtered

)

select
    series_key,
    date_key,
    realtime_start_date,
    realtime_end_date,
    value,
    fetched_at
from ranked
where rn = 1
