{% docs __overview__ %}
# AdventureWorks analytics

BigQuery analytics project with 13 raw sources, five staging models, and six marts.
Raw data is loaded from PostgreSQL by `elt_pipeline.py`; dbt then builds typed staging
relations and business reporting tables. Open the graph icon to explore model lineage.

## Reporting grains

| Mart | Grain | Business behavior |
| --- | --- | --- |
| fct_sales | Channel + sales order + line item | UNION ALL of Internet and Reseller sales; gross profit = sales amount − total product cost |
| dim_customer | Customer key | Customer attributes with source geography |
| dim_product | Product key (historical version) | Finished goods only; product IDs may repeat |
| dim_date | Calendar day / date key | Calendar attributes, quarter label, weekend flag |
| dim_reseller | Reseller key | Corporate attributes with source geography |
| dim_sales_territory | Territory key | Region, country, corporate group; preserves the NA placeholder |

## Transformation rules

- Staging dimensions are views; staged sales and all marts are tables.
- Marts use `gold_adventureworks`. Staging uses the selected profile's schema.
- Product end dates are the next version's start date minus one day within product ID;
  the final version remains open-ended. Original end dates remain in staging.
- Product color and size default to `Universal` and `N/A` for null or blank input.
- Customer and reseller keys in the sales fact are mutually exclusive by channel.
- Financial sales amounts use NUMERIC; product costs/prices and annual demographic
  revenue/income attributes use FLOAT64.

## Validation and warnings

Tests cover keys, grain, nulls, accepted values, source coverage, geographic mappings,
financial boundaries, and calendar/version continuity. Warnings preserve visibility of:

- Customer child counts where children at home exceeds total children.
- Missing product cost, price, or markup; product pricing below standard cost.
- Territory groups outside North America, Europe, and Pacific (including source NA).

Warnings do not repair source data. Other configured checks remain errors. Warning-as-error
options can make warning tests block a run. Documentation generation does not execute tests.

## Lineage and analytical joins

Graph edges describe SQL dependencies. `fct_sales` reads the two sales staging tables;
its model does not join the mart dimensions. Its relationship tests currently reference
staging product/date/customer and raw reseller tables. Sales territory is not projected
into the fact, so there is no direct fact-to-territory join key in this mart.

For reporting, join sales to product using product_key (not product_id), to dates using
order_date_key = date_key, and to customer/reseller using the appropriate channel key.
Product mart membership is restricted to finished goods; validate match coverage before
using an inner join. These analytical joins are separate from build dependencies.
{% enddocs %}
