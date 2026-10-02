-- Channel totals must survive dimension joins and monthly/product aggregation.
-- Exact NUMERIC comparison catches lost sales, fanout, and premature rounding.
with expected as (
    select
        sales_channel,
        sum(order_quantity) as units,
        sum(sales_amount) as revenue,
        sum(total_product_cost) as cost,
        sum(sales_amount) - sum(total_product_cost) as profit
    from {{ ref('fct_sales') }}
    group by sales_channel
), actual as (
    select
        sales_channel,
        sum(total_units_sold) as units,
        sum(gross_revenue_amount) as revenue,
        sum(total_product_cost) as cost,
        sum(gross_profit_amount) as profit
    from {{ ref('revenue_sales_performance') }}
    group by sales_channel
)
select e.sales_channel as expected_channel, a.sales_channel as actual_channel
from expected e
full outer join actual a on e.sales_channel = a.sales_channel
where e.sales_channel is null
   or a.sales_channel is null
   or e.units is distinct from a.units
   or e.revenue is distinct from a.revenue
   or e.cost is distinct from a.cost
   or e.profit is distinct from a.profit
