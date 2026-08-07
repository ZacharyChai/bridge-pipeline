with source as (

    select * from {{ source('raw_fred', 'series_metadata') }}

),

renamed as (

    select
        series_id,
        title,
        frequency,
        units,
        seasonal_adjustment,
        cast(observation_start as date) as observation_start_date,
        cast(observation_end as date) as observation_end_date,
        cast(fetched_at as timestamp) as fetched_at

    from source

)

select * from renamed
