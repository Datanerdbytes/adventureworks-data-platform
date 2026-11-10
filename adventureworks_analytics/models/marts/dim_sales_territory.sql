with raw_territory as (
    select * from {{ source('raw_adventureworks', 'dimsalesterritory') }}
)

select
    -- 🔑 Primary Key
    cast(salesterritorykey as bigint) as sales_territory_key,

    -- 🗺 Regional Hierarchy Attributes
    cast(salesterritoryalternatekey as bigint) as sales_territory_id,
    trim(salesterritoryregion) as territory_region,
    trim(salesterritorycountry) as territory_country,
    trim(salesterritorygroup) as territory_group

from raw_territory
