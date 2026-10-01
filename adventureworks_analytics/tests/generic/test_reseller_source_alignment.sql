{% test reseller_source_alignment(model) %}
-- Retain every reseller and match its own geography tuple and corporate fields.
select
    r.resellerkey as source_reseller_key,
    d.reseller_key as mart_reseller_key
from {{ source('raw_adventureworks', 'dimreseller') }} r
full outer join {{ model }} d
    on cast(r.resellerkey as int64) = d.reseller_key
left join {{ source('raw_adventureworks', 'dimgeography') }} g
    on r.geographykey = g.geographykey
where r.resellerkey is null
   or d.reseller_key is null
   or g.geographykey is null
   or d.reseller_id is distinct from r.reselleralternatekey
   or d.reseller_name is distinct from trim(r.resellername)
   or d.order_frequency is distinct from trim(r.orderfrequency)
   or d.number_of_employees is distinct from cast(r.numberemployees as int64)
   or d.annual_revenue is distinct from cast(r.annualrevenue as float64)
   or d.product_line is distinct from r.productline
   or d.year_opened is distinct from cast(r.yearopened as int64)
   or d.city is distinct from trim(g.city)
   or d.state_province_name is distinct from trim(g.stateprovincename)
   or d.country_region_name is distinct from trim(g.englishcountryregionname)
   or d.postal_code is distinct from trim(g.postalcode)
{% endtest %}
