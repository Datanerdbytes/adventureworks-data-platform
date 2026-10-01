{% test finished_product_coverage(model) %}
-- Every staged finished-good version must appear exactly once in the mart.
-- The separate unique test detects duplicate surrogate keys.
with expected as (
    select product_key, product_id, subcategory_name, category_name
    from {{ ref('stg_product') }}
    where product_status = 'Finished Good'
)
select e.product_key as expected_key, d.product_key as actual_key
from expected e
full outer join {{ model }} d on e.product_key = d.product_key
where e.product_key is null
   or d.product_key is null
   or d.product_id is distinct from e.product_id
   or d.subcategory_name is distinct from e.subcategory_name
   or d.category_name is distinct from e.category_name
{% endtest %}
