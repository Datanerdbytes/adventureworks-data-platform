{% test growth_trends_matches_fact(model) %}
-- Independently aggregate fact rows at the published grain. Compare every output
-- column in both directions; the YAML grain test checks duplicate multiplicities.
with expected as (
    select
        d.calendar_year,
        d.calendar_quarter_name,
        d.month_number,
        d.month_name,
        s.sales_channel,
        case when d.is_weekend_flag is true then 'Weekend' else 'Weekday' end as day_type_segment,
        round(sum(s.sales_amount), 2) as periodic_gross_revenue,
        sum(s.order_quantity) as periodic_units_sold,
        count(distinct s.sales_order_number) as periodic_orders_count,
        round(sum(s.sales_amount) / nullif(count(distinct s.sales_order_number), 0), 2) as transaction_aov
    from {{ ref('fct_sales') }} s
    inner join {{ ref('dim_date') }} d on s.order_date_key = d.date_key
    group by 1, 2, 3, 4, 5, 6
), actual as (
    select
        calendar_year, calendar_quarter_name, month_number, month_name,
        sales_channel, day_type_segment, periodic_gross_revenue,
        periodic_units_sold, periodic_orders_count, transaction_aov
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
select 'missing_or_changed' as mismatch_type, sales_channel from missing_or_changed
union all
select 'unexpected_or_changed' as mismatch_type, sales_channel from unexpected_or_changed
union all
-- Do not let the expected query reproduce silent losses from the model's join.
select 'unmapped_order_date' as mismatch_type, s.sales_channel
from {{ ref('fct_sales') }} s
left join {{ ref('dim_date') }} d on s.order_date_key = d.date_key
where d.date_key is null
{% endtest %}
