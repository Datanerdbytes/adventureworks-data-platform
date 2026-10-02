{{ config(materialized='ephemeral') }}

-- Shared sales-line enrichment. Keep unmatched keys and original precision.
select
    s.sales_order_number,
    s.sales_order_line_item,
    s.product_key,
    s.order_date_key,
    s.sales_channel,
    s.order_quantity,
    s.sales_amount,
    s.total_product_cost,
    coalesce(p.category_name, 'Unknown') as category_name,
    coalesce(p.subcategory_name, 'Unknown') as subcategory_name,
    coalesce(p.product_name, concat('Unknown product ', cast(s.product_key as string))) as product_name,
    p.model_name,
    coalesce(p.color, 'Unknown') as product_color,
    coalesce(p.size, 'Unknown') as product_size,
    coalesce(p.product_line, 'Unknown') as product_line,
    coalesce(p.class, 'Unknown') as product_class,
    coalesce(p.style, 'Unknown') as product_style
from {{ ref('fct_sales') }} s
left join {{ ref('dim_product') }} p on s.product_key = p.product_key
