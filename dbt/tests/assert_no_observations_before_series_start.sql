{#
    Singular test, Phase 5: no series has observations before its own documented start date.
    Genuine business logic, not schema: dim_series.observation_start_date and
    fct_observations.date_key are populated by two different pipelines (FRED's /fred/series
    metadata endpoint versus /fred/series/observations) that could in principle disagree --
    this proves they don't. A non-empty result means an observation date_day fell before that
    same series' own documented observation_start_date.
#}

select
    s.series_id,
    d.date_day as observation_date,
    s.observation_start_date as documented_start_date

from {{ ref("fct_observations") }} as f
inner join {{ ref("dim_series") }} as s on f.series_key = s.series_key
inner join {{ ref("dim_date") }} as d on f.date_key = d.date_key
where d.date_day < s.observation_start_date
