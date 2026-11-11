with raw_resellers as (
    select * from {{ source('raw_adventureworks', 'dimreseller') }}
),

raw_geography as (
    select * from {{ source('raw_adventureworks', 'dimgeography') }}
)

select
    -- 🔑 Primary Identification Key
    cast(r.resellerkey as bigint) as reseller_key,

    -- 🏢 Corporate Tracking Attributes
    r.reselleralternatekey as reseller_id,
    trim(r.resellername) as reseller_name,
    trim(r.orderfrequency) as order_frequency,
    cast(r.numberemployees as bigint) as number_of_employees,

    -- 💼 Wholesale Financial Context
    cast(r.annualrevenue as double) as annual_revenue,
    r.productline as product_line,
    cast(r.yearopened as bigint) as year_opened,

    -- 🏡 Enriched Geographic Hierarchy Attributes
    trim(g.city) as city,
    trim(g.stateprovincename) as state_province_name,
    trim(g.englishcountryregionname) as country_region_name,
    trim(g.postalcode) as postal_code

from raw_resellers r
left join raw_geography g
    on r.geographykey = g.geographykey
