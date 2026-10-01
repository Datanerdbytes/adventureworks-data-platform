with staged_customers as (
    select * from {{ ref('stg_customer') }}
),

raw_geography as (
    select * from {{ source('raw_adventureworks', 'dimgeography') }}
)

select
    -- 🔑 Primary Identification Key
    c.customer_key,

    -- 👤 Core Customer Biographical Attributes
    c.customer_id,
    c.title,
    c.first_name,
    c.middle_name,
    c.last_name,
    
    -- Consolidates separate naming fields into a beautiful, presentation-ready full name string
    trim(
        coalesce(c.title || ' ', '') || 
        c.first_name || ' ' || 
        coalesce(c.middle_name || ' ', '') || 
        c.last_name
    ) as full_name,

    c.birth_date,
    c.marital_status,
    c.gender,
    c.email_address,
    c.phone,

    -- 💰 Financial & Professional Demographics
    c.yearly_income,
    c.total_children,
    c.children_at_home,
    c.education_level,
    c.occupation,

    -- 🏡 Enriched Geographic Hierarchy Attributes (Denormalized out of raw_geography)
    trim(g.city) as city,
    trim(g.stateprovincename) as state_province_name,
    trim(g.englishcountryregionname) as country_region_name,
    trim(g.postalcode) as postal_code,

    -- 📆 Administrative Tracking Context
    c.date_first_purchase

from staged_customers c
left join raw_geography g 
    on c.geography_key = g.geographykey