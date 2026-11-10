{{ config(materialized='table') }}

with source_data as (
    select * from {{ source('raw_adventureworks', 'factresellersales') }}
)

select
    -- 🔑 Primary & Composite Keys
    salesordernumber as sales_order_number,
    cast(salesorderlinenumber as bigint) as sales_order_line_item,

    -- Dimension foreign keys
    cast(productkey as bigint) as product_key,
    cast(resellerkey as bigint) as reseller_key,
    cast(employeekey as bigint) as employee_key,
    cast(currencykey as bigint) as currency_key,
    cast(salesterritorykey as bigint) as sales_territory_key,

    -- Date dimension keys
    cast(orderdatekey as bigint) as order_date_key,
    cast(duedatekey as bigint) as due_date_key,
    cast(shipdatekey as bigint) as ship_date_key,

    -- 👤 Account & Transaction Context
    cast(promotionkey as bigint) as promotion_key,
    cast(revisionnumber as bigint) as revision_number,

    -- 📦 Transaction Quantities
    cast(orderquantity as bigint) as order_quantity,

    -- Fixed-point financial values for downstream arithmetic.
    -- Casting cannot recover precision already lost in the raw FLOAT64 values.
    cast(unitprice as decimal(38, 9)) as unit_price,
    cast(extendedamount as decimal(38, 9)) as extended_amount,
    cast(unitpricediscountpct as decimal(38, 9)) as unit_price_discount_percentage,
    cast(discountamount as decimal(38, 9)) as discount_amount,
    cast(productstandardcost as decimal(38, 9)) as product_standard_cost,
    cast(totalproductcost as decimal(38, 9)) as total_product_cost,
    cast(salesamount as decimal(38, 9)) as sales_amount,
    cast(taxamt as decimal(38, 9)) as tax_amount,
    cast(freight as decimal(38, 9)) as freight_amount,

    -- 🏷️ Shipping Trackers
    carriertrackingnumber as carrier_tracking_number,
    customerponumber as customer_po_number,

    -- 📅 Native Calendar Dimensions
    cast(orderdate as date) as order_date,
    cast(duedate as date) as due_date,
    cast(shipdate as date) as ship_date

from source_data
