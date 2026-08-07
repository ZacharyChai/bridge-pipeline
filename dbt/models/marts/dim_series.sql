with series as (

    select * from {{ ref("stg_series_metadata") }}

),

category as (

    select * from {{ ref("dim_series_category") }}

),

joined as (

    select
        series.series_id,
        series.title,
        series.frequency,
        series.units,
        series.seasonal_adjustment,
        series.observation_start_date,
        series.observation_end_date,
        category.category

    from series
    left join category on series.series_id = category.series_id

)

select
    {{ dbt_utils.generate_surrogate_key(["series_id"]) }} as series_key,
    *
from joined
