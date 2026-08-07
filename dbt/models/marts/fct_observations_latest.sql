{#
    Grain: one row per series, per observation date -- the single most recently known vintage,
    full stop. "Latest" is defined uniformly as the greatest realtime_start_date per
    (series_key, date_key), which works correctly whether the underlying series is genuinely
    vintage-tracked (many rows, take the newest) or current-value-only (exactly one row already
    -- see DECISIONS.md's Phase 2 entry on why that path can't just check
    realtime_end_date = '9999-12-31' the way a true vintage series can).
#}

with ranked as (

    select
        *,
        row_number() over (
            partition by series_key, date_key order by realtime_start_date desc
        ) as rn

    from {{ ref("fct_observations") }}

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
