with staged_products as (
    select * from {{ ref('stg_product') }}
),

finished_product_versions as (
    select
        *,
        lead(valid_from_date) over (
            partition by product_id
            order by valid_from_date, product_key
        ) as next_valid_from_date
    from staged_products
    where product_status = 'Finished Good'
)

select
    -- 🔑 Primary Key
    product_key,

    -- 🏷️ Identifiers & Descriptive Attributes
    product_id,
    product_name,
    model_name,
    
    -- Maps missing color strings to a clean 'Universal/No Color' label for dashboard filters
    coalesce(nullif(trim(color), ''), 'Universal') as color,
    
    -- Standardizes blank size strings into a readable text token
    coalesce(nullif(trim(size), ''), 'N/A') as size,
    size_unit_measure_code,

    -- 📊 Categorization Hierarchy
    subcategory_name,
    category_name,
    product_line,
    class,
    style,

    -- 💰 Financial Context
    standard_cost,
    list_price,
    (list_price - standard_cost) as markup_amount,

    -- 📆 Administrative Tracking Timelines
    valid_from_date,
    -- Inclusive end date; the last version remains open-ended.
    date_sub(next_valid_from_date, interval 1 day) as valid_to_date,
    current_status

from finished_product_versions
