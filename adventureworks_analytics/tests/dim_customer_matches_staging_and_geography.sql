-- A full join catches missing customers as well as unexpected mart rows.
-- Compare each customer's geography tuple, not independent lists of valid cities/countries.
select
    c.customer_key as staged_customer_key,
    d.customer_key as mart_customer_key
from {{ ref('stg_customer') }} c
full outer join {{ ref('dim_customer') }} d
    on c.customer_key = d.customer_key
left join {{ source('raw_adventureworks', 'dimgeography') }} g
    on c.geography_key = g.geographykey
where c.customer_key is null
   or d.customer_key is null
   or g.geographykey is null
   or d.customer_id is distinct from c.customer_id
   or d.city is distinct from trim(g.city)
   or d.state_province_name is distinct from trim(g.stateprovincename)
   or d.country_region_name is distinct from trim(g.englishcountryregionname)
   or d.postal_code is distinct from trim(g.postalcode)
