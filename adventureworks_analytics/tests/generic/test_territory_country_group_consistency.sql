{% test territory_country_group_consistency(model) %}
-- Multiple regions in a country must agree on its corporate macro group.
select territory_country
from {{ model }}
group by territory_country
having count(distinct territory_group) > 1
{% endtest %}
