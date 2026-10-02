# Model lineage

Generated from a locally parsed dbt manifest on 2026-10-02. Arrows show SQL build
dependencies, excluding test-only references. This is source-code lineage, not proof
that the current warehouse relations have been rebuilt.

```mermaid
flowchart LR
  subgraph g0["Raw sources"]
    n16["dimcurrency"]
    n17["dimcustomer"]
    n18["dimdate"]
    n19["dimemployee"]
    n20["dimgeography"]
    n21["dimproduct"]
    n22["dimproductcategory"]
    n23["dimproductsubcategory"]
    n24["dimpromotion"]
    n25["dimreseller"]
    n26["dimsalesterritory"]
    n27["factinternetsales"]
    n28["factresellersales"]
  end
  subgraph g1["Staging"]
    n11["stg_customer"]
    n12["stg_dim_date"]
    n13["stg_fact_internet_sales"]
    n14["stg_fact_reseller_sales"]
    n15["stg_product"]
  end
  subgraph g2["Core marts"]
    n0["dim_customer"]
    n1["dim_date"]
    n2["dim_product"]
    n3["dim_reseller"]
    n4["dim_sales_territory"]
    n5["fct_sales"]
  end
  subgraph g3["Shared enrichment (ephemeral)"]
    n6["int_product_sales"]
  end
  subgraph g4["Reporting models"]
    n7["marts_demographic_regional_insights"]
    n8["marts_growth_trends"]
    n9["marts_product_sales_performance"]
    n10["revenue_sales_performance"]
  end
  n11 --> n0
  n20 --> n0
  n12 --> n1
  n15 --> n2
  n20 --> n3
  n25 --> n3
  n26 --> n4
  n13 --> n5
  n14 --> n5
  n2 --> n6
  n5 --> n6
  n0 --> n7
  n4 --> n7
  n5 --> n7
  n1 --> n8
  n5 --> n8
  n6 --> n9
  n1 --> n10
  n6 --> n10
  n17 --> n11
  n18 --> n12
  n27 --> n13
  n28 --> n14
  n21 --> n15
  n22 --> n15
  n23 --> n15
```

Registered sources without model edges are retained for validation or future use.
`int_product_sales` is compiled into each consumer, not materialized as a table.

## Model inventory

Schema values below reflect the selected local profile; profile schemas can differ
between environments. Ephemeral models have no warehouse relation.

| Model | Materialization | Schema | Direct SQL inputs |
| --- | --- | --- | --- |
| dim_customer | table | gold_adventureworks | dimgeography, stg_customer |
| dim_date | table | gold_adventureworks | stg_dim_date |
| dim_product | table | gold_adventureworks | stg_product |
| dim_reseller | table | gold_adventureworks | dimgeography, dimreseller |
| dim_sales_territory | table | gold_adventureworks | dimsalesterritory |
| fct_sales | table | gold_adventureworks | stg_fact_internet_sales, stg_fact_reseller_sales |
| int_product_sales | ephemeral | — (no relation) | dim_product, fct_sales |
| marts_demographic_regional_insights | table | gold_adventureworks | dim_customer, dim_sales_territory, fct_sales |
| marts_growth_trends | view | silver_adventureworks | dim_date, fct_sales |
| marts_product_sales_performance | table | gold_adventureworks | int_product_sales |
| revenue_sales_performance | table | gold_adventureworks | dim_date, int_product_sales |
| stg_customer | view | silver_adventureworks | dimcustomer |
| stg_dim_date | view | silver_adventureworks | dimdate |
| stg_fact_internet_sales | table | silver_adventureworks | factinternetsales |
| stg_fact_reseller_sales | table | silver_adventureworks | factresellersales |
| stg_product | view | silver_adventureworks | dimproduct, dimproductcategory, dimproductsubcategory |

## Reporting joins

| Fact field | Dimension field | Notes |
| --- | --- | --- |
| product_key | dim_product.product_key | Historical version key; finished goods only. Shared enrichment uses a left join to retain unmatched sales. |
| order_date_key | dim_date.date_key | Order-date role. |
| customer_key | dim_customer.customer_key | Internet channel. |
| reseller_key | dim_reseller.reseller_key | Reseller channel. |
| sales_territory_key | dim_sales_territory.sales_territory_key | Preserved from both staged facts; used by demographics. |

Fact relationship tests do not mean the fact SQL joins those dimensions. The diagram
does include the actual joins performed by shared enrichment and reporting models.

## Reporting changes

- `marts_product_sales_performance` replaces `marts_product_inventory_analytics`
  at product-key/channel grain. The old warehouse relation requires separate retirement.
- The monthly revenue model retains its existing grain and now shares product enrichment.
- Growth remains a profile-schema view because its SQL is outside `models/marts/`.
- Product-key coverage tests flag unknown dimension matches without removing sales.

See [reporting grains and validation](PROJECT_GUIDE.md) and
[product sales migration and metric rules](PRODUCT_SALES.md).

## Refresh

Regenerate this snapshot after dependency changes. For the interactive graph, use
the [offline documentation workflow](PROJECT_GUIDE.md#selective-rebuilds-and-offline-documentation)
or `dbt docs generate --static` for a warehouse-backed catalog.
