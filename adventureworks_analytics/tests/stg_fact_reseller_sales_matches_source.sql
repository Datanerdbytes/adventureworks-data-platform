-- Validate the materialized data against every expected source field.
-- EXCEPT DISTINCT compares nulls safely. Row-count and grain tests separately
-- detect duplicate/missing row multiplicities that set comparison cannot detect.
with expected as (
    select
        salesordernumber as sales_order_number,
        cast(salesorderlinenumber as int64) as sales_order_line_item,
        cast(productkey as int64) as product_key,
        cast(resellerkey as int64) as reseller_key,
        cast(employeekey as int64) as employee_key,
        cast(currencykey as int64) as currency_key,
        cast(salesterritorykey as int64) as sales_territory_key,
        cast(orderdatekey as int64) as order_date_key,
        cast(duedatekey as int64) as due_date_key,
        cast(shipdatekey as int64) as ship_date_key,
        cast(promotionkey as int64) as promotion_key,
        cast(revisionnumber as int64) as revision_number,
        cast(orderquantity as int64) as order_quantity,
        cast(unitprice as numeric) as unit_price,
        cast(extendedamount as numeric) as extended_amount,
        cast(unitpricediscountpct as numeric) as unit_price_discount_percentage,
        cast(discountamount as numeric) as discount_amount,
        cast(productstandardcost as numeric) as product_standard_cost,
        cast(totalproductcost as numeric) as total_product_cost,
        cast(salesamount as numeric) as sales_amount,
        cast(taxamt as numeric) as tax_amount,
        cast(freight as numeric) as freight_amount,
        carriertrackingnumber as carrier_tracking_number,
        customerponumber as customer_po_number,
        cast(orderdate as date) as order_date,
        cast(duedate as date) as due_date,
        cast(shipdate as date) as ship_date
    from {{ source('raw_adventureworks', 'factresellersales') }}
), actual as (
    select
        sales_order_number,
        sales_order_line_item,
        product_key,
        reseller_key,
        employee_key,
        currency_key,
        sales_territory_key,
        order_date_key,
        due_date_key,
        ship_date_key,
        promotion_key,
        revision_number,
        order_quantity,
        unit_price,
        extended_amount,
        unit_price_discount_percentage,
        discount_amount,
        product_standard_cost,
        total_product_cost,
        sales_amount,
        tax_amount,
        freight_amount,
        carrier_tracking_number,
        customer_po_number,
        order_date,
        due_date,
        ship_date
    from {{ ref('stg_fact_reseller_sales') }}
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
