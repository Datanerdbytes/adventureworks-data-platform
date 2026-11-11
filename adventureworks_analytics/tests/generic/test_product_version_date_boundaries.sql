{% test product_version_date_boundaries(model) %}
-- Check adjacent inclusive ranges for both gaps and overlaps, including an
-- incorrectly open historical version or a closed final version.
with versions as (
    select
        *,
        lead(valid_from_date) over (
            partition by product_id
            order by valid_from_date, product_key
        ) as next_start
    from {{ model }}
)
select *
from versions
{% set next_column = "next_start" %}
{% set valid_column = "valid_to_date" %}
where (next_start is null and valid_to_date is not null)
   or (next_start is not null and (
       valid_to_date is null
       or {{ qe_date_diff(next_column, valid_column, 'DAY') }} != 1
   ))
{% endtest %}
