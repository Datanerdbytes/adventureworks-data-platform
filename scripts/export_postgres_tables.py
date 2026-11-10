"""Extract the Postgres source tables into committed Parquet files.

One-time build step for the portable rebuild: the migration is only
reproducible from a clean clone if the raw extract travels with the repository
(the BigQuery project this pipeline fed is unreachable without live billing).
The Postgres instance itself stays the source of truth; these Parquet files are
the shipped snapshot the offline dbt-duckdb build reads.

Bounded batches; no warehouse clients. Run from the repository root:

    uv run python scripts/export_postgres_tables.py
"""

from pathlib import Path

import pyarrow as pa
import sqlalchemy as sa

from db_connector import get_postgres_engine
from elt_staging import DEFAULT_BATCH_SIZE, arrow_type, write_parquet_batches

# Mirrors elt_pipeline.TABLES_TO_MIGRATE so the extract covers exactly the
# tables the BigQuery pipeline carried.
TABLES_TO_EXTRACT = (
    "dimcurrency",
    "dimcustomer",
    "dimdate",
    "dimemployee",
    "dimgeography",
    "dimproduct",
    "dimproductcategory",
    "dimproductsubcategory",
    "dimpromotion",
    "dimreseller",
    "dimsalesterritory",
    "factinternetsales",
    "factresellersales",
)

OUTPUT_DIR = Path("data/raw/adventureworks_dw")

# Payload images no model, test, or dashboard page selects; 57 KB of binary per
# row in dimemployee alone, kept out of the repository snapshot deliberately.
# Everything else mirrors the source table exactly.
EXCLUDED_COLUMNS = {
    "dimemployee": {"employeephoto"},
    "dimsalesterritory": {"salesterritoryimage"},
}


def reflect_arrow_schema(columns):
    """Build the pyarrow schema from the source column metadata."""
    fields = [
        pa.field(column.name, arrow_type(column.type), column.nullable)
        for column in columns
    ]
    return pa.schema(fields)


def reflect_source_table(table_name, columns):
    excluded = EXCLUDED_COLUMNS.get(table_name, set())
    mapped_columns = [
        sa.schema.Column(
            column["name"], column["type"], nullable=column.get("nullable", True)
        )
        for column in columns
        if column["name"] not in excluded
    ]
    if not mapped_columns:
        raise ValueError(f"Source table {table_name} has no columns after exclusions.")
    return mapped_columns


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = get_postgres_engine()
    summary = []
    with engine.connect() as conn:
        for table_name in TABLES_TO_EXTRACT:
            inspected = sa.inspect(conn).get_columns(table_name)
            if not inspected:
                raise ValueError(
                    f"Source table {table_name} has no reflectable columns."
                )
            mapped_columns = reflect_source_table(table_name, inspected)
            arrow_schema = reflect_arrow_schema(mapped_columns)
            destination = OUTPUT_DIR / f"{table_name}.parquet"
            result = conn.execute(
                sa.select(
                    sa.schema.Table(table_name, sa.MetaData(), *mapped_columns)
                ).execution_options(yield_per=DEFAULT_BATCH_SIZE)
            )
            rows = write_parquet_batches(result, arrow_schema, destination)
            summary.append((table_name, rows))
    for table_name, rows in summary:
        print(
            f"{table_name:<22} {rows:>7} rows -> {OUTPUT_DIR / f'{table_name}.parquet'}"
        )
    print(f"Extracted {len(summary)} tables.")


if __name__ == "__main__":
    main()
