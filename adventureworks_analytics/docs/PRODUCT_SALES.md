# Product sales reporting

`marts_product_sales_performance` replaces `marts_product_inventory_analytics`.
It reports all-time sales at **product_key and sales_channel** grain. Historical
product versions remain separate. It does not report stock levels or inventory
turnover; those require inventory snapshots or movements.

`revenue_sales_performance` retains its monthly product-name/channel grain and
existing columns. Both marts use the ephemeral `int_product_sales` model for
product enrichment. They independently count distinct orders from sales lines,
so neither sums the other's non-additive order counts.

## Metric and data-quality rules

- `product_purchasing_orders_count` replaces `associated_orders_count`. An order
  can contain several products; never sum these counts for category or overall
  order counts. Count distinct orders from `fct_sales` at the requested grain,
  keeping channels separate.
- The product mart retains unmatched fact product keys with Unknown attributes.
  Its product-key relationship test flags missing dimension matches separately
  from the fact reconciliation test, which checks that sales are preserved.
- Revenue, cost, and profit retain source precision. Format monetary values to
  two decimals for display. Calculate broader margins as total profit divided
  by total revenue, not by averaging row margins. Zero revenue gives a null margin.
- Unsold products are absent. Use the product catalog for catalog coverage.

For example, this BigQuery query calculates category counts and weighted margins
directly from facts (replace the project/dataset identifiers for your environment):

```sql
select
    coalesce(p.category_name, 'Unknown') as category_name,
    s.sales_channel,
    count(distinct s.sales_order_number) as category_orders_count,
    sum(s.sales_amount) as revenue,
    sum(s.sales_amount) - sum(s.total_product_cost) as profit,
    (sum(s.sales_amount) - sum(s.total_product_cost))
        / nullif(sum(s.sales_amount), 0) * 100 as margin_percentage
from `PROJECT.DATASET.fct_sales` s
left join `PROJECT.DATASET.dim_product` p on s.product_key = p.product_key
group by 1, 2
```

## Deployment

From the dbt project directory, deploy the two output marts after their input
tables are current:

```sh
dbt build --select marts_product_sales_performance revenue_sales_performance
```

The ephemeral enrichment is compiled into both queries automatically. Update
external consumers to the new model name, order-count column, and product-key
grain. Renaming a dbt model does not remove the old warehouse table; retire that
table separately after consumers migrate. No warehouse tables were changed as
part of this source-code update.
