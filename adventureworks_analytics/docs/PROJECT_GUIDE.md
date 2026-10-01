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

## Working with the project

Run these commands from `adventureworks_analytics` with the repository virtual environment activated.
The BigQuery profile is named `adventureworks_analytics`; credentials and connection settings belong
in the local dbt profile/environment and are not included in this documentation.

```sh
dbt deps
dbt parse --no-partial-parse
dbt build
dbt test --select dim_product
dbt docs generate --static
dbt docs serve --port 8080
```

`dbt build` materializes models and runs their tests. `dbt test` requires existing relations.
The source-loading script replaces raw tables with `WRITE_TRUNCATE`; run it only when a raw-data
refresh is intended. dbt commands do not invoke that loader automatically.

## Documentation and lineage

- [Build lineage and model inventory](LINEAGE.md)
- [Project validation guide](../README.md)
- [Standalone interactive dbt documentation](../target/static_index.html)

Open `static_index.html` in a browser, select a model, and use the graph icon to inspect upstream
and downstream dependencies. It embeds the generated manifest and catalog. The regular site can
also be served with `dbt docs serve`. Artifacts in `target/` are regenerated and removed by `dbt clean`.
The lineage diagram is a snapshot; regenerate docs after SQL or YAML changes.

## Validation inventory

The following counts describe configured tests, not a fresh full-project test execution.
Documentation generation reads catalog metadata and compiles SQL; it does not prove data tests pass.

This snapshot contains **346 tests**, including **6 warning-level tests**.

| Mart | Directly attached tests | Warning-level tests |
| --- | --- | --- |
| dim_customer | 46 | 1 |
| dim_date | 10 | 0 |
| dim_product | 41 | 4 |
| dim_reseller | 38 | 0 |
| dim_sales_territory | 21 | 1 |
| fct_sales | 16 | 0 |
