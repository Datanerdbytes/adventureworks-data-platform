# AdventureWorks analytics

BigQuery staging and reporting marts for AdventureWorks sales data.

- [Project documentation and operating guide](docs/PROJECT_GUIDE.md)
- [Model lineage diagram and inventory](docs/LINEAGE.md)
- [Product sales semantics and migration](docs/PRODUCT_SALES.md)
- [Interactive dbt documentation and lineage](target/static_index.html)
- [Offline source documentation and lineage](target/docs-offline/static_index.html)

Generate fresh documentation with `dbt docs generate --static`; open `target/static_index.html` or run `dbt docs serve --port 8080`.

### Source data quality

Run all source checks from this directory:

```sh
dbt test --select source:raw_adventureworks
```

The tests in `models/staging/sources.yml` cover all 13 source tables:

- `not_empty`: each table must contain at least one row (a reusable generic test in `tests/generic`).
- `not_null` and `unique`: dimension surrogate keys must be present and unique.
- `dbt_utils.unique_combination_of_columns`: sales order number and line number together identify each sales row; both fields must also be present.
- `relationships`: sales dimension references and the customer/geography/product hierarchy must resolve to existing source keys. Sales foreign keys also have `not_null` tests. Dimension relationship tests allow null references, such as products without a subcategory.
- Existing customer/product accepted-value and whitespace checks remain in place.

These are baseline expectations for the AdventureWorks schema. A `FAIL` reports a data-quality issue; an `ERROR` means the check could not execute (for example, a missing column or connection problem). Empty-table tests report one failure per empty table; uniqueness tests count duplicate key groups; other tests generally count offending rows. Review the individual test output and `target/run_results.json` for results. Passing these checks does not establish that every field is complete or accurate.

Use `dbt parse --no-partial-parse` to validate the configuration without querying the warehouse. Install project packages with `dbt deps` if needed.

### Reseller sales validation

`stg_fact_reseller_sales` materializes as a table, retaining one row per sales order and line item. Financial fields use `NUMERIC`; the raw `FLOAT64` precision cannot be recovered by casting.

```sh
dbt run --select stg_fact_reseller_sales
dbt test --select stg_fact_reseller_sales
```

The configured tests cover required keys and core fields, a nonempty table, order-line uniqueness, and dimension relationships. Product keys reference `stg_product`; other dimension keys reference raw dimension tables until staging models exist for them.

Validation also checks positive order quantities, discount fractions between zero and one, due/ship dates on or after the order date, and date keys matching their calendar dates. These expectations describe sales transactions; review them if returns or other transaction types are introduced.

Source reconciliation compares row counts and all 27 transformed fields in both directions, including nulls, against `factresellersales`. It uses the same intended type conversions, so it checks preservation after conversion rather than lossless conversion from raw floating-point values. Run against a stable source snapshot: loading new raw data after materialization can legitimately cause reconciliation failures.

### Customer child-count policy

`dim_customer` preserves the source values for `total_children` and `children_at_home`.
Both counts must be non-null and nonnegative; violations fail validation.
When children at home exceeds total children, `dim_customer_child_counts_consistent`
reports a warning for source-data review. Neither count is adjusted automatically,
because the available data does not establish which value is correct. The warning
does not mean the inconsistent counts are suitable for household analysis.

Run customer validation with `dbt test --select dim_customer`. Warnings allow the
normal run to succeed; dbt warning-as-error options can still make them blocking.

### Product mart validation

Run `dbt test --select dim_product` after building the product models. The tests
in `models/marts/marts.yml` cover surrogate-key uniqueness, required identifiers,
finished-goods coverage, category references, descriptive values, financial values,
markup arithmetic, and validity-date ordering. The `finished_product_coverage`
test also checks each product's identifier and category pair against staging.

The grain is one row per `product_key`; `product_id` can repeat across historical
versions. A null end date is allowed. Missing or blank colors and sizes become
`Universal` and `N/A`. Costs and prices must be finite and nonnegative; below-cost
pricing produces a warning for review rather than an automatic price correction. Missing
cost, price, and markup also produce warnings; the missing values remain null.

Product validity ranges use inclusive dates. Within each `product_id`, versions
are ordered by `valid_from_date`; each end date is the next start date minus one
day, and the last version has a null end date. This mart rule replaces source end
dates while preserving the original dates in staging. Tests reject duplicate
start dates, reversed ranges, gaps, overlaps, and closed final versions.

### Reseller mart validation

Run `dbt build --select dim_reseller` to materialize and validate the reseller mart.
Tests in `models/marts/marts.yml` require one row per reseller key and business ID,
complete source coverage, nonblank corporate and geographic attributes, and exact
alignment with each reseller's source geography. Corporate names need not be unique.
Order frequency is restricted to the existing source codes `A`, `Q`, and `S`;
new codes require a reviewed update to that list.

Revenue must be finite and nonnegative, employee counts must be nonnegative, and
opening years must be between 1 and the current year. All three fields are required.
No arbitrary upper limit is imposed on revenue or company size. Postal codes remain
text so international formats and leading zeros are preserved.

### Sales territory validation

Territory IDs and keys must be unique and non-null, regional mappings must match
the source, and each country must map consistently to one corporate group. All
three groups (`North America`, `Europe`, `Pacific`) must be represented. Values
outside that list produce warnings, retaining visibility of the source `NA` placeholder.

### Reporting model validation

Dedicated YAML files define tests for revenue, growth, demographics, and product
sales. See the [current model/test inventory](docs/PROJECT_GUIDE.md#validation-inventory).
`marts_product_sales_performance` replaces the inventory-named model and preserves
unmatched product sales. Its dimension relationship test flags missing matches;
its separate fact reconciliation test checks financial totals and distinct orders.
The shared `int_product_sales` model also feeds monthly revenue reporting.

Demographics requires the rebuilt `fct_sales.sales_territory_key`. Internet unknown
attributes are not wholesale labels. Growth reports monthly weekday/weekend sales
and AOV, not growth rates or moving averages, and remains a profile-schema view.

Build commands and the no-warehouse documentation workflow are in the
[operating guide](docs/PROJECT_GUIDE.md#selective-rebuilds-and-offline-documentation).
