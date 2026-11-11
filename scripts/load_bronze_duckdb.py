"""Load the committed Parquet snapshot into the DuckDB bronze schema.

One-time build step for the portable rebuild. The Parquet files under
``data/raw/adventureworks_dw`` mirror the Postgres source tables, and this
loader materializes them as the ``raw_adventureworks`` schema inside the
offline build database that ``dbt build --profiles-dir adventureworks_analytics``
reads. The BigQuery ``raw_adventureworks`` dataset was the same landing zone;
the types carry over unchanged because the Parquet snapshot kept the source
types.

Run from the repository root before ``dbt build``:

    uv run python -B scripts/load_bronze_duckdb.py

Pass ``--fresh`` to rebuild the file from scratch.
"""

import argparse
from pathlib import Path

import duckdb

BRONZE_TABLES = (
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

SNAPSHOT_DIR = Path("data/raw/adventureworks_dw")
BUILD_PATH = Path("adventureworks_analytics/build/analytics.duckdb")
BRONZE_SCHEMA = "raw_adventureworks"


def load_snapshot(connection):
    for table_name in BRONZE_TABLES:
        source = SNAPSHOT_DIR / f"{table_name}.parquet"
        if not source.exists():
            raise FileNotFoundError(f"Snapshot file missing: {source}")
        # Parquet stores the source types (DECIMAL, DATE, TIMESTAMP), so a
        # straight read preserves the bronze contract without a hand-written DDL.
        # Identifiers come only from the hard-coded BRONZE_TABLES tuple.
        connection.execute(
            f"CREATE TABLE {BRONZE_SCHEMA}.{table_name} AS "  # nosec B608
            f"SELECT * FROM read_parquet('{source}');"  # nosec B608
        )
        rows = connection.execute(
            f"SELECT count(*) FROM {BRONZE_SCHEMA}.{table_name};"  # nosec B608
        ).fetchone()[0]
        print(f"{table_name:<22} {rows:>7} rows")


def finalize(connection):
    connection.execute("CHECKPOINT;")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Rebuild the bronze file even if a database already exists there.",
    )
    arguments = parser.parse_args()
    if BUILD_PATH.exists() and not arguments.fresh and BUILD_PATH.stat().st_size > 0:
        raise SystemExit(
            f"{BUILD_PATH} already exists. Re-run with --fresh to rebuild it."
        )
    if arguments.fresh and BUILD_PATH.exists():
        BUILD_PATH.unlink()
    BUILD_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(BUILD_PATH))
    try:
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {BRONZE_SCHEMA};")
        load_snapshot(connection)
        finalize(connection)
    finally:
        connection.close()
    print(f"Bronze build written to {BUILD_PATH}.")


if __name__ == "__main__":
    main()
