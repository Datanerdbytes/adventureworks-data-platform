{{ config(materialized='table') }}

with source_data as (
    select * from {{ source('raw_adventureworks', 'factresellersales') }}
)

select
    -- 🔑 Primary & Composite Keys
    salesordernumber as sales_order_number,
    cast(salesorderlinenumber as int64) as sales_order_line_item,

    -- Dimension foreign keys
    cast(productkey as int64) as product_key,
    cast(resellerkey as int64) as reseller_key,
    cast(employeekey as int64) as employee_key,
    cast(currencykey as int64) as currency_key,
    cast(salesterritorykey as int64) as sales_territory_key,

    -- Date dimension keys
    cast(orderdatekey as int64) as order_date_key,
    cast(duedatekey as int64) as due_date_key,
    cast(shipdatekey as int64) as ship_date_key,

    -- 👤 Account & Transaction Context
    cast(promotionkey as int64) as promotion_key,
    cast(revisionnumber as int64) as revision_number,

    -- 📦 Transaction Quantities
    cast(orderquantity as int64) as order_quantity,

    -- Fixed-point financial values for downstream arithmetic.
    -- Casting cannot recover precision already lost in the raw FLOAT64 values.
    cast(unitprice as numeric) as unit_price,
    cast(extendedamount as numeric) as extended_amount,
    cast(unitpricediscountpct as numeric) as unit_price_discount_percentage,
    cast(discountamount as numeric) as discount_amount,
    cast(productstandardcost as numeric) as product_standard_cost,
    cast(totalproductcost as numeric) as total_product_cost,
    cast(salesamount as numeric) as sales_amount,
    cast(taxamt as numeric) as tax_amount,
    cast(freight as numeric) as freight_amount,

    -- 🏷️ Shipping Trackers
    carriertrackingnumber as carrier_tracking_number,
    customerponumber as customer_po_number,

    -- 📅 Native Calendar Dimensions
    cast(orderdate as date) as order_date,
    cast(duedate as date) as due_date,
    cast(shipdate as date) as ship_date

from source_data
