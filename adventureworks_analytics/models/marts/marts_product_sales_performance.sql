-- One row per product version key and channel, across all order dates.
select
    product_key,
    category_name,
    subcategory_name,
    product_name,
    model_name,
    product_color,
    product_size,
    product_line,
    product_class,
    product_style,
    sales_channel,
    -- Orders overlap across products. Calculate broader counts from fct_sales.
    count(distinct sales_order_number) as product_purchasing_orders_count,
    sum(order_quantity) as total_units_sold,
    sum(sales_amount) as gross_sales_revenue,
    sum(total_product_cost) as aggregated_production_cost,
    sum(sales_amount) - sum(total_product_cost) as generated_gross_profit,
    round(
        (sum(sales_amount) - sum(total_product_cost))
        / nullif(sum(sales_amount), 0) * 100, 2
    ) as realized_profit_margin_percentage
from {{ ref('int_product_sales') }}
group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11
