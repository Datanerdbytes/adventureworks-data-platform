"""Bounded, read-only previews of explicit analytics tables, shared across users."""

from datetime import date, datetime
from decimal import Decimal
import math
from typing import TypedDict

from google.cloud import bigquery
from revenue_kpis import cache, validate_warehouse_identifiers
from warehouse_cache import warehouse_memoize

MAX_PREVIEW_ROWS = 500


class TableSpec(TypedDict):
    table: str
    grain: str
    order: tuple[str, ...]
    columns: tuple[tuple[str, str, str], ...]


TABLES: dict[str, TableSpec] = {
    "Products": {
        "table": "dim_product",
        "grain": "product version",
        "order": ("product_key",),
        "columns": (
            ("product_key", "Product key", "number"),
            ("product_id", "Product ID", "text"),
            ("product_name", "Product", "text"),
            ("category_name", "Category", "text"),
            ("subcategory_name", "Subcategory", "text"),
            ("color", "Color", "text"),
            ("size", "Size", "text"),
            ("standard_cost", "Standard cost (USD)", "number"),
            ("list_price", "List price (USD)", "number"),
            ("valid_from_date", "Valid from", "date"),
            ("valid_to_date", "Valid to", "date"),
        ),
    },
    "Customers": {
        "table": "dim_customer",
        "grain": "customer",
        "order": ("customer_key",),
        "columns": (
            ("customer_key", "Customer key", "number"),
            ("full_name", "Customer", "text"),
            ("city", "City", "text"),
            ("state_province_name", "State / province", "text"),
            ("country_region_name", "Country / region", "text"),
            ("occupation", "Occupation", "text"),
            ("education_level", "Education", "text"),
            ("date_first_purchase", "First purchase", "date"),
        ),
    },
    "Sales": {
        "table": "fct_sales",
        "grain": "channel / order / line item",
        "order": ("sales_channel", "sales_order_number", "sales_order_line_item"),
        "columns": (
            ("sales_channel", "Channel", "text"),
            ("sales_order_number", "Order", "text"),
            ("sales_order_line_item", "Line item", "number"),
            ("product_key", "Product key", "number"),
            ("order_date_key", "Order date key", "number"),
            ("customer_key", "Customer key", "number"),
            ("reseller_key", "Reseller key", "number"),
            ("order_quantity", "Quantity", "number"),
            ("sales_amount", "Revenue (USD)", "number"),
            ("total_product_cost", "Cost (USD)", "number"),
            ("gross_profit_amount", "Gross profit (USD)", "number"),
        ),
    },
}


def table_sql(project, dataset, name):
    validate_warehouse_identifiers(project, dataset)
    if not isinstance(name, str) or name not in TABLES:
        raise ValueError("Unknown warehouse preview table")
    spec = TABLES[name]
    fields = ", ".join(f"`{field}`" for field, _, _ in spec["columns"])
    order = ", ".join(f"`{field}`" for field in spec["order"])
    return (
        f"SELECT {fields} FROM `{project}.{dataset}.{spec['table']}` "
        f"ORDER BY {order} LIMIT @preview_limit"
    )


def preview_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@warehouse_memoize(cache, timeout=60)
def load_table_preview(project, dataset, name):
    query = table_sql(project, dataset, name)
    with bigquery.Client(project=project) as client:
        job = client.query(
            query,
            job_config=bigquery.QueryJobConfig(
                maximum_bytes_billed=100 * 1024 * 1024,
                use_query_cache=True,
                query_parameters=[
                    bigquery.ScalarQueryParameter(
                        "preview_limit", "INT64", MAX_PREVIEW_ROWS + 1
                    )
                ],
            ),
        )
        try:
            # A sentinel distinguishes a complete small table from a capped preview.
            result = list(job.result(timeout=20, max_results=MAX_PREVIEW_ROWS + 1))
        except TimeoutError:
            job.cancel()
            raise
    rows = [
        {field: preview_value(row[field]) for field, _, _ in TABLES[name]["columns"]}
        for row in result[:MAX_PREVIEW_ROWS]
    ]
    return {"rows": rows, "capped": len(result) > MAX_PREVIEW_ROWS}


def preview_columns(name):
    return [
        {
            "field": field,
            "headerName": label,
            "minWidth": 150 if kind != "number" else 125,
            "filter": (
                "agNumberColumnFilter" if kind == "number" else "agTextColumnFilter"
            ),
            **(
                {"type": "numericColumn", "cellDataType": "number"}
                if kind == "number"
                else {"cellDataType": "text"}
            ),
            "editable": False,
        }
        for field, label, kind in TABLES[name]["columns"]
    ]
