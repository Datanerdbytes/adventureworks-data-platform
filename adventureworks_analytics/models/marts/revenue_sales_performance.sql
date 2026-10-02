with sales_core as (
    select * from {{ ref('int_product_sales') }}
),

date_dimension as (
    select date_key, calendar_year, calendar_quarter_name, month_name
    from {{ ref('dim_date') }}
)

select
    -- 🕒 Time Dimensions
    d.calendar_year,
    d.calendar_quarter_name,
    d.month_name,

    -- 🏷️ Channel & Product Hierarchy Context
    s.sales_channel,
    s.category_name as product_category,
    s.subcategory_name as product_subcategory,
    s.product_name as product_name,

    -- 📈 Core Aggregated Volume Performance Metrics
    -- Orders overlap between products; do not sum this count across products.
    count(distinct s.sales_order_number) as product_purchasing_orders_count,
    sum(s.order_quantity) as total_units_sold,

    -- 💰 Financial Revenue Metrics
    -- Preserve fixed-point precision for downstream rollups; format at display time.
    sum(s.sales_amount) as gross_revenue_amount,
    sum(s.total_product_cost) as total_product_cost,
    
    -- Calculated Financial Performance Margins
    sum(s.sales_amount) - sum(s.total_product_cost) as gross_profit_amount,
    round(
        (sum(s.sales_amount) - sum(s.total_product_cost)) / nullif(sum(s.sales_amount), 0) * 100, 
        2
    ) as gross_profit_margin_percentage,

    -- 📊 Operational Business Efficiency Indicators
    -- Product spend per purchasing order, not the value of the entire basket.
    round(sum(s.sales_amount) / nullif(count(distinct s.sales_order_number), 0), 2) as product_revenue_per_purchasing_order

from sales_core s
inner join date_dimension d 
    on s.order_date_key = d.date_key

group by 1, 2, 3, 4, 5, 6, 7
