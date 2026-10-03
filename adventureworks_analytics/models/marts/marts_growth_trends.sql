with sales_core as (
    select * from {{ ref('fct_sales') }}
),

date_dimension as (
    select * from {{ ref('dim_date') }}
),

daily_channel_aggregates as (
    select
        d.calendar_year,
        d.calendar_quarter_name,
        d.month_number,
        d.month_name,
        d.is_weekend_flag,
        s.sales_channel,
        
        -- Financial Volume Rollups
        sum(s.sales_amount) as daily_gross_revenue,
        sum(s.order_quantity) as daily_units_sold,
        count(distinct s.sales_order_number) as daily_orders_count

    from sales_core s
    inner join date_dimension d 
        on s.order_date_key = d.date_key
    group by 1, 2, 3, 4, 5, 6
)

select
    calendar_year,
    calendar_quarter_name,
    month_number,
    month_name,
    sales_channel,
    
    -- ⏱️ Temporal Segmentations
    case 
        when is_weekend_flag is true then 'Weekend'
        else 'Weekday'
    end as day_type_segment,

    -- 💰 Consolidated Aggregations
    round(sum(daily_gross_revenue), 2) as periodic_gross_revenue,
    sum(daily_units_sold) as periodic_units_sold,
    sum(daily_orders_count) as periodic_orders_count,

    -- 📊 Moving Performance Averages
    round(sum(daily_gross_revenue) / nullif(sum(daily_orders_count), 0), 2) as transaction_aov

from daily_channel_aggregates
group by 1, 2, 3, 4, 5, 6
