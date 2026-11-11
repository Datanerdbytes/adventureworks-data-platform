"""Fail when the shipped runtime database drifts from the dbt build.

The app reads ``my-dash-app/data/analytics.duckdb``, a committed artifact
produced by ``scripts/export_gold_duckdb.py``. If a model changes and the
artifact is not re-exported, the app would serve stale numbers while the
models say otherwise. This compares the committed artifact against the dbt
build and exits non-zero on any difference.

Usage:
    uv run python scripts/verify_shipped_gold.py
    uv run python scripts/verify_shipped_gold.py \
        --built adventureworks_analytics/build/analytics.duckdb \
        --shipped my-dash-app/data/analytics.duckdb
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import duckdb

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_BUILT = REPO_ROOT / "adventureworks_analytics" / "build" / "analytics.duckdb"
DEFAULT_SHIPPED = REPO_ROOT / "my-dash-app" / "data" / "analytics.duckdb"

SCHEMA_TABLES = {
    "gold_adventureworks": (
        "dim_customer",
        "dim_date",
        "dim_product",
        "dim_reseller",
        "dim_sales_territory",
        "fct_sales",
        "marts_demographic_regional_insights",
        "marts_growth_trends",
        "marts_product_sales_performance",
        "revenue_sales_performance",
    ),
    "silver_adventureworks": ("stg_fact_reseller_sales",),
}

SOURCE_SCHEMAS = {
    "gold_adventureworks": "gold_adventureworks",
    "silver_adventureworks": "main",
}

# Money and volume columns compared per table. Decimal and double columns are
# summed with a tolerance because the two files may store them with different
# physical types but must hold the same values.
NUMERIC_SUM_COLUMNS = {
    ("gold_adventureworks", "fct_sales"): (
        "sales_amount",
        "total_product_cost",
        "order_quantity",
    ),
    ("gold_adventureworks", "revenue_sales_performance"): (
        "gross_revenue_amount",
        "total_product_cost",
        "total_units_sold",
    ),
    ("gold_adventureworks", "marts_product_sales_performance"): (
        "gross_sales_revenue",
        "aggregated_production_cost",
        "total_units_sold",
    ),
    ("gold_adventureworks", "marts_growth_trends"): ("periodic_units_sold",),
    ("gold_adventureworks", "marts_demographic_regional_insights"): (
        "total_units_sold",
        "gross_revenue_amount",
    ),
    ("silver_adventureworks", "stg_fact_reseller_sales"): (
        "sales_amount",
        "total_product_cost",
        "order_quantity",
    ),
}


def numeric_sum(
    connection: duckdb.DuckDBPyConnection, table: str, column: str
) -> float:
    result = connection.execute(
        f"SELECT COALESCE(SUM({column}), 0) FROM {table}"  # nosec B608
    ).fetchone()
    return float(result[0]) if result is not None else 0.0


def row_count(connection: duckdb.DuckDBPyConnection, table: str) -> int:
    result = connection.execute(
        f"SELECT COUNT(*) FROM {table}"  # nosec B608
    ).fetchone()
    return int(result[0]) if result is not None else 0


def compare(built_path: pathlib.Path, shipped_path: pathlib.Path) -> list[str]:
    differences: list[str] = []

    for label, path in (("built", built_path), ("shipped", shipped_path)):
        if not path.exists():
            differences.append(f"{label} database missing: {path}")
    if differences:
        return differences

    built = duckdb.connect(str(built_path), read_only=True)
    shipped = duckdb.connect(str(shipped_path), read_only=True)
    try:
        for schema, tables in SCHEMA_TABLES.items():
            built_schema = SOURCE_SCHEMAS[schema]
            for table in tables:
                built_table = f"{built_schema}.{table}"
                shipped_table = f"{schema}.{table}"
                built_rows = row_count(built, built_table)
                shipped_rows = row_count(shipped, shipped_table)
                if built_rows != shipped_rows:
                    differences.append(
                        f"{shipped_table}: row count built={built_rows:,} "
                        f"shipped={shipped_rows:,}"
                    )
                    continue

                for column in NUMERIC_SUM_COLUMNS.get((schema, table), ()):
                    built_sum = numeric_sum(built, built_table, column)
                    shipped_sum = numeric_sum(shipped, shipped_table, column)
                    if abs(built_sum - shipped_sum) > 0.01:
                        differences.append(
                            f"{shipped_table}.{column}: built={built_sum:,.4f} "
                            f"shipped={shipped_sum:,.4f}"
                        )
    finally:
        built.close()
        shipped.close()

    return differences


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--built", type=pathlib.Path, default=DEFAULT_BUILT)
    parser.add_argument("--shipped", type=pathlib.Path, default=DEFAULT_SHIPPED)
    args = parser.parse_args(argv)

    differences = compare(
        args.built.expanduser().resolve(), args.shipped.expanduser().resolve()
    )

    if differences:
        print("Shipped runtime artifact is out of date:")
        for difference in differences:
            print(f"  - {difference}")
        print("Re-run scripts/export_gold_duckdb.py and commit the result.")
        return 1

    print("Shipped runtime artifact matches the dbt build.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
