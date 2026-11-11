"""In-memory DuckDB fixtures for the app's gold and silver schema names.

The runtime SQL reads the committed artifact's ``gold_adventureworks`` and
``silver_adventureworks`` schemas. Tests declare their small input tables in the
default schema and this helper mirrors each table as a view under both names, so
the production SQL runs unchanged instead of being rewritten for SQLite.
"""

import duckdb

SCHEMAS = ("gold_adventureworks", "silver_adventureworks")


def connect(script=""):
    """Return one in-memory database with both artifact schemas available."""
    database = duckdb.connect(":memory:")
    for schema in SCHEMAS:
        database.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    if script:
        database.execute(script)
    mirror(database)
    return database


def mirror(database):
    """Expose every default-schema table under the shipped schema names."""
    tables = [
        row[0]
        for row in database.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_type = 'BASE TABLE'"
        ).fetchall()
    ]
    for table in tables:
        for schema in SCHEMAS:
            database.execute(
                f'CREATE OR REPLACE VIEW {schema}."{table}" '
                f'AS SELECT * FROM main."{table}"'
            )


def rows(database, sql, parameters=None):
    """Fetch dict rows keyed by the cursor's column names."""
    cursor = database.execute(sql, parameters or {})
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
