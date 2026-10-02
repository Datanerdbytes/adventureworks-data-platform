with internet_sales as (
    select * from {{ ref('stg_fact_internet_sales') }}
),

reseller_sales as (
    select * from {{ ref('stg_fact_reseller_sales') }}
),

unified_sales as (
    -- 🛒 Combine Internet Checkout Transactions
    select
        sales_order_number,
        sales_order_line_item,
        product_key,
        order_date_key,
        sales_territory_key,
        'Internet' as sales_channel,
        customer_key,
        null as reseller_key,  -- Internet sales do not have reseller anchors
        order_quantity,
        sales_amount,
        total_product_cost
    from internet_sales

    union all

    -- 🏢 Combine Wholesale B2B Corporate Orders
    select
        sales_order_number,
        sales_order_line_item,
        product_key,
        order_date_key,
        sales_territory_key,
        'Reseller' as sales_channel,
        null as customer_key, -- Reseller orders do not have a B2C customer anchor
        reseller_key,
        order_quantity,
        sales_amount,
        total_product_cost
    from reseller_sales
)

select
    -- 🔑 Composite Primary Identification Elements
    sales_order_number,
    sales_order_line_item,
    sales_channel,

    -- 🔗 Core Dimensions Integration Indexes
    product_key,
    order_date_key,
    sales_territory_key,
    customer_key,
    reseller_key,

    -- 📈 Key Financial Metrics
    order_quantity,
    sales_amount,
    total_product_cost,
    (sales_amount - total_product_cost) as gross_profit_amount

from unified_sales
