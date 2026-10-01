{% test not_empty(model) %}

-- Return one failure when the source has no rows; stop scanning after one row.
select 1 as empty_source
from (select 1 as sentinel) as placeholder
where not exists (
    select 1
    from {{ model }}
    limit 1
)

{% endtest %}
