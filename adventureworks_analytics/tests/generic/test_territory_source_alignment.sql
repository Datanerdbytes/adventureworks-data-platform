{% test territory_source_alignment(model) %}
select r.salesterritorykey as source_key, d.sales_territory_key as mart_key
from {{ source('raw_adventureworks', 'dimsalesterritory') }} r
full outer join {{ model }} d
    on cast(r.salesterritorykey as int64) = d.sales_territory_key
where r.salesterritorykey is null
   or d.sales_territory_key is null
   or d.sales_territory_id is distinct from cast(r.salesterritoryalternatekey as int64)
   or d.territory_region is distinct from trim(r.salesterritoryregion)
   or d.territory_country is distinct from trim(r.salesterritorycountry)
   or d.territory_group is distinct from trim(r.salesterritorygroup)
{% endtest %}
