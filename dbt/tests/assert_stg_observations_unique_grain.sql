-- Singular test: stg_observations' declared grain is one row per
-- (series_id, obs_date, realtime_start_date) — see _staging.yml and DECISIONS.md's Phase 2
-- entry for why realtime_start is part of the key, not just series_id + obs_date.
-- dbt's built-in `unique` test only covers a single column, so a composite-key check needs
-- either dbt_utils (installed in Phase 5) or a singular test like this one.
--
-- A non-empty result means the grain is violated: dbt fails the test if this returns rows.

select
    series_id,
    obs_date,
    realtime_start_date,
    count(*) as n

from {{ ref('stg_observations') }}
group by series_id, obs_date, realtime_start_date
having count(*) > 1
