"""Read-only SQL access to the shipped DuckDB analytics artifact.

The BigQuery warehouse this app queried is gone. The same dbt models now build
into one committed DuckDB file that ships with the app, so the runtime read
path is a local file instead of a paid query. Filters and limits bind as named
``$name`` placeholders; filters are always bound values, never interpolated
strings.
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import duckdb

DEFAULT_ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "analytics.duckdb"
GOLD_SCHEMA = "gold_adventureworks"


def artifact_path():
    """Resolve the shipped artifact, honouring the deployment override."""
    override = os.environ.get("GOLD_DATABASE_PATH")
    return Path(override).expanduser() if override else DEFAULT_ARTIFACT_PATH


def _missing_artifact_error(path):
    return FileNotFoundError(
        f"Analytics artifact not found at {path}. Build it with "
        "scripts/load_bronze_duckdb.py plus dbt and export it with "
        "scripts/export_gold_duckdb.py."
    )


def validate_artifact():
    """Fail fast when the deployed artifact is missing or empty."""
    path = artifact_path()
    if not path.is_file():
        raise _missing_artifact_error(path)
    try:
        connection = duckdb.connect(str(path), read_only=True)
    except duckdb.Error as error:
        raise RuntimeError(
            f"Analytics artifact at {path} is not a readable DuckDB database."
        ) from error
    try:
        table_count = connection.execute(
            "SELECT COUNT(*) FROM information_schema.tables " "WHERE table_schema = ?",
            [GOLD_SCHEMA],
        ).fetchone()[0]
    except duckdb.Error as error:
        raise RuntimeError(
            f"Analytics artifact at {path} is not a readable DuckDB database."
        ) from error
    finally:
        connection.close()
    if not table_count:
        raise RuntimeError(f"Analytics artifact at {path} has no {GOLD_SCHEMA} tables.")
    return path


def query_rows(sql, parameters=None):
    """Run one read-only query and return dict rows with matching column keys."""
    path = artifact_path()
    if not path.exists():
        raise _missing_artifact_error(path)
    bound: dict[str, Any] | list[Any]
    if not parameters:
        bound = []
    elif isinstance(parameters, Mapping):
        # Named $name placeholders bind through a mapping.
        bound = dict(parameters)
    else:
        bound = list(parameters)
    connection = duckdb.connect(str(path), read_only=True)
    try:
        cursor = connection.execute(sql, bound)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        connection.close()
