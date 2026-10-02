# AdventureWorks analytics

BigQuery analytics project with 13 raw sources and 16 models: five staging models,
one ephemeral intermediate model, six core marts, and four reporting models.
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
| int_product_sales | Channel + sales order + line item | Shared product enrichment; preserves unmatched keys; ephemeral SQL, not a warehouse table |
| revenue_sales_performance | Year + month + channel + category/subcategory/product name | Monthly sales; combines product versions with identical names and hierarchy |
| marts_product_sales_performance | Product key + channel | All-time product sales; historical versions stay separate; replaces the inventory-named model |
| marts_growth_trends | Year + month + channel + weekday/weekend | Monthly segmented sales and AOV; no moving average or growth-rate calculation |
| marts_demographic_regional_insights | Territory group/country/region + customer state/city + channel + occupation/education/gender/income bracket | All-time demographic sales; Internet unknowns remain distinct from wholesale labels |

## Transformation rules

- Staging dimensions are views; staged sales and models under `models/marts/` are tables.
- Models under `models/marts/` use `gold_adventureworks`. Staging uses the selected
  profile's schema. `marts_growth_trends` currently lives directly under `models/`,
  so it is a view in the profile schema, not a Gold table.
- `int_product_sales` is ephemeral and compiled into its consumers; no relation is created.
- Product end dates are the next version's start date minus one day within product ID;
  the final version remains open-ended. Original end dates remain in staging.
- Product color and size default to `Universal` and `N/A` for null or blank input.
- Customer and reseller keys in the sales fact are mutually exclusive by channel.
- `fct_sales` retains `sales_territory_key` from both channels. Rebuild the fact
  before dependent reports when adding or changing its projected columns.
- Both product-sales reports share `int_product_sales`; its left join preserves
  sales missing a finished-goods match with Unknown attributes and the source key.
- Product-sales revenue, cost, and profit retain source precision. Growth and
  demographics still round financial totals per segment.
- Product purchasing-order counts overlap across products. Calculate broader
  distinct orders from facts by channel; recompute margins from summed amounts.
- Missing or blank Internet demographic text and missing income become Unknown;
  reseller attributes use Wholesale/Reseller or N/A - Wholesale.
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
its model does not join the mart dimensions. Its relationship tests reference
staging product/date/customer, raw reseller, and `dim_sales_territory` for the new
`sales_territory_key`. Test references do not add SQL build edges.

For reporting, join sales to product using product_key (not product_id), to dates using
order_date_key = date_key, to territory using sales_territory_key, and to
customer/reseller using the appropriate channel key.
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
- [Product sales semantics and migration](PRODUCT_SALES.md)
- [Offline documentation snapshot](../target/docs-offline/static_index.html)
- [Standalone interactive dbt documentation](../target/static_index.html)

Open `static_index.html` in a browser, select a model, and use the graph icon to inspect upstream
and downstream dependencies. It embeds the generated manifest and catalog. The regular site can
also be served with `dbt docs serve`. Artifacts in `target/` are regenerated and removed by `dbt clean`.
The lineage diagram is a snapshot; regenerate docs after SQL or YAML changes.

## Selective rebuilds and offline documentation

Selecting a downstream model alone does not rebuild its upstream tables. For the
territory-key change, rebuild the fact alongside the demographics report:

```sh
dbt build --select fct_sales marts_demographic_regional_insights
```

Deploy the product-sales rename and shared enrichment with:

```sh
dbt build --select marts_product_sales_performance revenue_sales_performance
```

These commands materialize warehouse tables. The source documentation update does
not execute them. The old inventory-named table is not automatically dropped;
migrate external consumers before retiring it.

The offline site includes source definitions, configured tests, and lineage, but
no live warehouse catalog, column types, or row statistics. Generate it without
warehouse access (parse first so `--no-compile` has a current manifest):

```sh
dbt parse --no-partial-parse --target-path target/docs-offline
dbt docs generate --static --no-compile --empty-catalog --target-path target/docs-offline
```

This separate output directory preserves the existing warehouse-backed catalog.
Neither parse nor offline docs generation proves that models build or data tests pass.

## Validation inventory

Manifest snapshot dated 2026-10-02: **430 configured tests**, including **6 warning-level
tests**. Counts describe configuration, not a fresh production test execution.
The table counts tests attached to each reporting/core model; standalone SQL
reconciliation tests also contribute to the project total.

| Model | Attached tests | Warning-level tests |
| --- | --- | --- |
| dim_customer | 46 | 1 |
| dim_date | 10 | 0 |
| dim_product | 41 | 4 |
| dim_reseller | 38 | 0 |
| dim_sales_territory | 21 | 1 |
| fct_sales | 18 | 0 |
| marts_demographic_regional_insights | 25 | 0 |
| marts_growth_trends | 20 | 0 |
| marts_product_sales_performance | 24 | 0 |
| revenue_sales_performance | 12 | 0 |
