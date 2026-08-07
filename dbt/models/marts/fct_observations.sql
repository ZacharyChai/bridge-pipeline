{#
    Grain: one row per series, per observation date, per vintage -- see DECISIONS.md's Phase 4
    entry. Every FRED/ALFRED revision is its own row; nothing is collapsed here. This is the one
    fact that carries full history -- fct_observations_latest and
    fct_observations_point_in_time (both derived from this) are the simplified views.
#}

with observations as (

    select * from {{ ref("stg_observations") }}

),

series as (

    select
        series_key,
        series_id
    from {{ ref("dim_series") }}

),

dates as (

    select
        date_key,
        date_day
    from {{ ref("dim_date") }}

),

joined as (

    select
        series.series_key,
        dates.date_key,
        observations.realtime_start_date,
        observations.realtime_end_date,
        observations.value,
        observations.fetched_at

    from observations
    inner join series on observations.series_id = series.series_id
    inner join dates on observations.obs_date = dates.date_day

)

select * from joined
