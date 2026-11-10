"""Export the dbt-built schemas into the standalone database the app ships.

The dbt build produces one DuckDB file with bronze, staging and gold schemas.
Only what the app's loaders read is needed at runtime, and the app must run
without write access to its data files, so the shipped artifact is a separate
file holding those tables alone: the 10 ``gold_adventureworks`` marts/tables
plus the ``silver_adventureworks`` fact that the wholesale fulfillment loader
joins. Schema names keep the BigQuery dataset names the loader SQL expects.

Usage:
    uv run python scripts/export_gold_duckdb.py
    uv run python scripts/export_gold_duckdb.py \
        --built adventureworks_analytics/build/analytics.duckdb \
        --out my-dash-app/data/analytics.duckdb
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import duckdb

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_BUILT = REPO_ROOT / "adventureworks_analytics" / "build" / "analytics.duckdb"
DEFAULT_OUT = REPO_ROOT / "my-dash-app" / "data" / "analytics.duckdb"

# Schema and table names mirror the BigQuery datasets the loader SQL reads.
# Staging models build into the dbt target schema (main), while the shipped
# artifact presents the wholesale loader's staging fact under the
# silver_adventureworks dataset name it expects.
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


def export_tables(built_path: pathlib.Path, out_path: pathlib.Path) -> None:
    if not built_path.exists():
        raise FileNotFoundError(f"Build database not found: {built_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.unlink(missing_ok=True)

    connection = duckdb.connect(str(out_path))
    try:
        connection.execute(f"ATTACH '{built_path.as_posix()}' AS src (READ_ONLY)")
        for schema, tables in SCHEMA_TABLES.items():
            connection.execute(f"CREATE SCHEMA {schema}")
            for table in tables:
                source_schema = SOURCE_SCHEMAS[schema]
                # Identifiers come only from the hard-coded SCHEMA_TABLES map.
                connection.execute(
                    f"CREATE TABLE {schema}.{table} AS "  # nosec B608
                    f"SELECT * FROM src.{source_schema}.{table}"  # nosec B608
                )
                result = connection.execute(
                    f"SELECT COUNT(*) FROM {schema}.{table}"  # nosec B608
                ).fetchone()
                rows = result[0] if result is not None else 0
                print(f"  {schema}.{table:<46} {rows:>9,} rows")
        connection.execute("DETACH src")
        connection.execute("CHECKPOINT")
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--built", type=pathlib.Path, default=DEFAULT_BUILT)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    built_path = args.built.expanduser().resolve()
    out_path = args.out.expanduser().resolve()

    print(f"Exporting runtime tables from {built_path} to {out_path}")
    export_tables(built_path, out_path)
    print(f"Wrote {out_path} ({out_path.stat().st_size / 1_000_000:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
