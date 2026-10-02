{% test product_sales_matches_fact(model) %}
-- Independent fact-only aggregation detects lost sales and dimension join fanout.
with expected as (
    select
        product_key, sales_channel,
        count(distinct sales_order_number) as product_purchasing_orders_count,
        sum(order_quantity) as total_units_sold,
        sum(sales_amount) as gross_sales_revenue,
        sum(total_product_cost) as aggregated_production_cost,
        sum(sales_amount) - sum(total_product_cost) as generated_gross_profit,
        round((sum(sales_amount) - sum(total_product_cost))
            / nullif(sum(sales_amount), 0) * 100, 2) as realized_profit_margin_percentage
    from {{ ref('fct_sales') }}
    group by product_key, sales_channel
), actual as (
    select product_key, sales_channel, product_purchasing_orders_count,
        total_units_sold, gross_sales_revenue, aggregated_production_cost,
        generated_gross_profit, realized_profit_margin_percentage
    from {{ model }}
), missing_or_changed as (
    select * from expected
    except distinct
    select * from actual
), unexpected_or_changed as (
    select * from actual
    except distinct
    select * from expected
)
select 'missing_or_changed' as mismatch_type, * from missing_or_changed
union all
select 'unexpected_or_changed' as mismatch_type, * from unexpected_or_changed
{% endtest %}
