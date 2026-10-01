{% test required_values_present(model, column_name, values) %}
-- Complements accepted_values: every required value must also be represented.
with required_values as (
    {% for value in values %}
    select '{{ value | replace("'", "''") }}' as required_value
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)
select r.required_value
from required_values r
where not exists (
    select 1 from {{ model }} d
    where d.{{ column_name }} = r.required_value
)
{% endtest %}
