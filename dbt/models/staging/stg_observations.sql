with source as (

    select * from {{ source('raw_fred', 'observations') }}

),

renamed as (

    select
        series_id,
        cast(obs_date as date) as obs_date,
        cast(realtime_start as date) as realtime_start_date,
        cast(realtime_end as date) as realtime_end_date,
        cast(fetched_at as timestamp) as fetched_at,
        -- FRED's "." missing-value marker: try_cast turns it (and any other unparseable
        -- value) into null rather than erroring the whole model. See DECISIONS.md's Phase 3
        -- entry for why null, not a dropped row: staging renames and casts, it doesn't filter.
        try_cast(value as double) as value

    from source

)

select * from renamed
