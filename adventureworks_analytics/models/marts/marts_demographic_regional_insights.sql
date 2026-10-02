with sales_core as (
    select * from {{ ref('fct_sales') }}
),

customer_dimension as (
    select * from {{ ref('dim_customer') }}
),

territory_dimension as (
    select * from {{ ref('dim_sales_territory') }}
)

select
    -- 🗺️ Geographic Hierarchy Attributes
    t.territory_group,
    t.territory_country,
    t.territory_region,
    case when s.sales_channel = 'Reseller' then 'Wholesale/Reseller'
        else coalesce(nullif(trim(c.state_province_name), ''), 'Unknown')
    end as customer_state_province,
    case when s.sales_channel = 'Reseller' then 'Wholesale/Reseller'
        else coalesce(nullif(trim(c.city), ''), 'Unknown')
    end as customer_city,

    -- 👤 B2C Customer Demographics Profile Context
    s.sales_channel,
    case when s.sales_channel = 'Reseller' then 'N/A - Wholesale'
        else coalesce(nullif(trim(c.occupation), ''), 'Unknown')
    end as customer_occupation,
    case when s.sales_channel = 'Reseller' then 'N/A - Wholesale'
        else coalesce(nullif(trim(c.education_level), ''), 'Unknown')
    end as customer_education_level,
    case when s.sales_channel = 'Reseller' then 'N/A - Wholesale'
        else coalesce(nullif(trim(c.gender), ''), 'Unknown')
    end as customer_gender,
    
    -- Income Brackets to group purchasing power easily on charts
    case 
        when s.sales_channel = 'Reseller' then 'N/A - Wholesale'
        when c.yearly_income is null then 'Unknown'
        when c.yearly_income < 30000 then 'Low Income (<30k)'
        when c.yearly_income >= 30000 and c.yearly_income < 70000 then 'Middle Income (30k-70k)'
        when c.yearly_income >= 70000 and c.yearly_income < 100000 then 'High Income (70k-100k)'
        else 'Very High Income (100k+)'
    end as customer_income_bracket,

    -- 💰 Consolidated Volume & Financial Performance Metrics
    count(distinct s.sales_order_number) as total_orders_count,
    sum(s.order_quantity) as total_units_sold,
    round(sum(s.sales_amount), 2) as gross_revenue_amount,
    round(sum(s.sales_amount) - sum(s.total_product_cost), 2) as gross_profit_amount

from sales_core s
left join customer_dimension c 
    on s.customer_key = c.customer_key
inner join territory_dimension t 
    on s.sales_territory_key = t.sales_territory_key

group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
