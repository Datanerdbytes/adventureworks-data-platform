import argparse
import os
import re
import sys
import tempfile
from contextlib import suppress
from pathlib import Path
from dotenv import load_dotenv
import sqlalchemy as sa
import pyarrow as pa
import pyarrow.parquet as pq
from google.cloud import bigquery
from db_connector import get_postgres_engine
from elt_staging import (
    DEFAULT_BATCH_SIZE,
    MAX_BATCH_SIZE,
    arrow_type,
    write_parquet_batches,
)

PRODUCTION_PROJECT_ID = "quantum-echo-data-eng-prod"
DEFAULT_REGION = "asia-east2"
WRITE_DISPOSITION = "WRITE_TRUNCATE"

TABLES_TO_MIGRATE = [
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
]


class PipelineConfigurationError(Exception):
    """Raised when pipeline configuration is missing or contradictory."""

    pass


class PipelineConfirmationError(Exception):
    """Raised when production confirmation requirements are not met."""

    pass


def _load_env():
    """Load environment variables from .env file."""
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path, override=False)


def _is_interactive():
    """Check if stdin is a TTY (interactive)."""
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def _validate_project(value):
    # Use canonical project IDs, not numeric aliases, for production detection.
    if not isinstance(value, str) or not re.fullmatch(
        r"[a-z][a-z0-9-]{4,28}[a-z0-9]", value
    ):
        raise PipelineConfigurationError("Invalid destination project ID.")


def _validate_dataset(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,1024}", value):
        raise PipelineConfigurationError("Invalid destination dataset ID.")


def _validate_options(dry_run, confirm_production, destination, interactive):
    if type(dry_run) is not bool:
        raise PipelineConfigurationError("dry_run must be a boolean.")
    if type(confirm_production) is not bool:
        raise PipelineConfirmationError("confirm_production must be a boolean.")
    if interactive is not None and type(interactive) is not bool:
        raise PipelineConfigurationError("interactive must be a boolean or None.")
    if destination is not None:
        if not isinstance(destination, str) or destination.count(".") != 1:
            raise PipelineConfirmationError(
                "Destination confirmation must be project.dataset."
            )
        project, dataset = destination.split(".")
        try:
            _validate_project(project)
            _validate_dataset(dataset)
        except PipelineConfigurationError:
            raise PipelineConfirmationError(
                "Invalid destination confirmation."
            ) from None


def _safe_error_category(error):
    # Select fixed labels rather than printing exception messages, SQL, or URLs.
    if isinstance(error, (ConnectionError, sa.exc.DBAPIError)):
        return "database connection or query failure"
    if isinstance(error, TimeoutError):
        return "operation timed out"
    return "operation failed"


def resolve_destination_config():
    """Resolve and validate the effective destination project/dataset.

    Returns:
        tuple: (project_id, dataset_id, effective_destination_string)

    Raises:
        PipelineConfigurationError: on missing or contradictory configuration.
    """
    project_id = os.getenv("GBQ_PROJECT_ID")
    dataset_id = os.getenv("GBQ_DATASET_ID")

    if not project_id:
        raise PipelineConfigurationError(
            "GBQ_PROJECT_ID is not set. Cannot determine destination project."
        )

    if not dataset_id:
        raise PipelineConfigurationError(
            "GBQ_DATASET_ID is not set. Cannot determine destination dataset."
        )

    _validate_project(project_id)
    if "." in dataset_id:
        if dataset_id.count(".") != 1:
            raise PipelineConfigurationError(
                "GBQ_DATASET_ID must be dataset or project.dataset."
            )
        qualified_project, dataset_id = dataset_id.split(".")
        _validate_project(qualified_project)
        if qualified_project != project_id:
            raise PipelineConfigurationError(
                f"GBQ_DATASET_ID project prefix '{qualified_project}' conflicts with "
                f"GBQ_PROJECT_ID '{project_id}'. Refusing contradictory configuration."
            )
    _validate_dataset(dataset_id)

    effective_destination = f"{project_id}.{dataset_id}"
    return project_id, dataset_id, effective_destination


def is_production_destination(project_id):
    """Recognize quantum-echo-data-eng-prod as production regardless of ENVIRONMENT label."""
    return project_id == PRODUCTION_PROJECT_ID


def validate_confirmation(
    project_id,
    dataset_id,
    effective_destination,
    confirm_production,
    destination,
    interactive,
):
    """Validate confirmation requirements for production writes.

    Must be called BEFORE source reads / client creation / destructive submission.

    Args:
        project_id: Resolved destination project ID.
        dataset_id: Resolved destination dataset ID.
        effective_destination: Full effective destination string (project.dataset).
        confirm_production: Value of --confirm-production flag.
        destination: Value of --destination flag.
        interactive: Whether interactive prompts are allowed.

    Raises:
        PipelineConfirmationError: if confirmation requirements are not met.
    """
    _validate_options(False, confirm_production, destination, interactive)
    _validate_project(project_id)
    _validate_dataset(dataset_id)
    if effective_destination != f"{project_id}.{dataset_id}":
        raise PipelineConfigurationError("Inconsistent effective destination.")
    if destination is not None and destination != effective_destination:
        raise PipelineConfirmationError(
            "Destination confirmation mismatch. Refusing to proceed."
        )
    if not is_production_destination(project_id):
        return

    if confirm_production is not True:
        raise PipelineConfirmationError(
            "Production destination detected. "
            "--confirm-production is required to proceed with WRITE_TRUNCATE."
        )

    if not destination:
        raise PipelineConfirmationError(
            "Production destination detected. "
            "--destination <exact_destination> is required to confirm the exact target."
        )


def _print_dry_run(
    project_id,
    dataset_id,
    effective_destination,
    is_production,
    confirm_production,
    destination,
):
    """Print side-effect-free preflight information."""
    print("=" * 70)
    print("ELT PIPELINE DRY-RUN PREFLIGHT")
    print("=" * 70)
    print(f"Destination project:  {project_id}")
    print(f"Destination dataset:   {dataset_id}")
    print(f"Effective destination:  {effective_destination}")
    print(f"Region:                {DEFAULT_REGION}")
    print(f"Write disposition:     {WRITE_DISPOSITION}")
    print(f"Production target:     {'YES' if is_production else 'NO'}")
    print(f"Tables to migrate:     {len(TABLES_TO_MIGRATE)}")
    for t in TABLES_TO_MIGRATE:
        print(f"  - {t}")
    print()
    print("Required confirmations for production writes:")
    print(f"  --confirm-production: {'SET' if confirm_production else 'NOT SET'}")
    print(f"  --destination:        {destination if destination else 'NOT SET'}")
    if is_production:
        if confirm_production and destination == effective_destination:
            print(
                "  Status: ALL CONFIRMATIONS PROVIDED (dry-run only, no jobs submitted)"
            )
        else:
            print("  Status: CONFIRMATIONS MISSING - will refuse to execute")
    print()
    print("No load jobs will be submitted. No network or credentials required.")
    print("=" * 70)


def _validate_batch_size(batch_size):
    if type(batch_size) is not int or not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise PipelineConfigurationError(
            f"batch_size must be an integer between 1 and {MAX_BATCH_SIZE}."
        )


def spool_table(connection, table_name, path, batch_size=DEFAULT_BATCH_SIZE):
    """Reflect a fixed source table and stream it to a typed Parquet file."""
    _validate_batch_size(batch_size)
    if table_name not in TABLES_TO_MIGRATE:
        raise PipelineConfigurationError("Unknown source table.")
    columns = sa.inspect(connection).get_columns(table_name, schema="public")
    schema = pa.schema(
        [pa.field(col["name"], arrow_type(col["type"])) for col in columns]
    )
    quote = connection.dialect.identifier_preparer.quote
    selected = ", ".join(quote(col["name"]) for col in columns)
    query = sa.text(f"SELECT {selected} FROM public.{table_name}")  # nosec B608
    streaming = connection.execution_options(
        stream_results=True, yield_per=batch_size, max_row_buffer=batch_size
    )
    result = streaming.execute(query)
    try:
        return write_parquet_batches(result, schema, path, batch_size)
    finally:
        with suppress(Exception):
            result.close()


def bigquery_schema(arrow_schema):
    """Preserve source logical types instead of Parquet timestamp autodetection."""
    fields = []
    for field in arrow_schema:
        kind = field.type
        if pa.types.is_timestamp(kind):
            target_type = "TIMESTAMP" if kind.tz else "DATETIME"
        elif pa.types.is_date(kind):
            target_type = "DATE"
        elif pa.types.is_time(kind):
            target_type = "TIME"
        elif pa.types.is_boolean(kind):
            target_type = "BOOLEAN"
        elif pa.types.is_integer(kind):
            target_type = "INTEGER"
        elif pa.types.is_floating(kind):
            target_type = "FLOAT"
        elif pa.types.is_binary(kind):
            target_type = "BYTES"
        elif pa.types.is_string(kind):
            target_type = "STRING"
        else:
            raise PipelineConfigurationError("Unsupported staged column type.")
        fields.append(bigquery.SchemaField(field.name, target_type))
    return fields


def run_elt_migration(
    dry_run=False,
    confirm_production=False,
    destination=None,
    interactive=None,
    batch_size=DEFAULT_BATCH_SIZE,
):
    """Run the ELT migration with safeguards.

    Args:
        dry_run: If True, print preflight info and exit without executing loads.
        confirm_production: Explicit production confirmation flag.
        destination: Exact destination confirmation string.
        interactive: Whether to allow interactive prompts.
                     If None, auto-detected from stdin.
        batch_size: Bounded source rows per fetch (1 to MAX_BATCH_SIZE).

    Raises:
        PipelineConfigurationError: on missing or contradictory configuration.
        PipelineConfirmationError: if production confirmation requirements are not met.
    """
    _validate_options(dry_run, confirm_production, destination, interactive)
    _validate_batch_size(batch_size)
    _load_env()

    if interactive is None:
        interactive = _is_interactive()

    project_id, dataset_id, effective_destination = resolve_destination_config()
    is_production = is_production_destination(project_id)

    if dry_run:
        _print_dry_run(
            project_id,
            dataset_id,
            effective_destination,
            is_production,
            confirm_production,
            destination,
        )
        return

    validate_confirmation(
        project_id,
        dataset_id,
        effective_destination,
        confirm_production,
        destination,
        interactive,
    )

    if is_production:
        print(
            "WARNING: Software confirmation checks do not replace the "
            "repository's required multi-turn human approval process."
        )

    print("Connecting to source (PostgreSQL) and initializing BigQuery Client...")
    pg_engine = get_postgres_engine()
    bq_client = None
    try:
        bq_client = bigquery.Client(project=project_id)
        print(f"\nStarting database migration to {DEFAULT_REGION}...")
        successful_tables = []
        failed_tables = []
        for table_name in TABLES_TO_MIGRATE:
            temporary = None
            connection = None
            try:
                print(f"Processing table: {table_name}...")
                temporary = tempfile.TemporaryDirectory(prefix="adventureworks-elt-")
                path = Path(temporary.name) / "table.parquet"
                connection = pg_engine.connect()
                try:
                    row_count = spool_table(connection, table_name, path, batch_size)
                finally:
                    with suppress(Exception):
                        connection.close()
                    connection = None
                if not row_count:
                    print(f"  Skipping {table_name}: Table is empty.")
                    continue
                table_ref = f"{project_id}.{dataset_id}.{table_name}"
                job_config = bigquery.LoadJobConfig(
                    write_disposition=WRITE_DISPOSITION,
                    source_format=bigquery.SourceFormat.PARQUET,
                    schema=bigquery_schema(pq.read_schema(path)),
                )
                print(f"  -> Loading {row_count} staged rows to BigQuery...")
                with path.open("rb") as source:
                    job = bq_client.load_table_from_file(
                        source,
                        table_ref,
                        job_config=job_config,
                        location=DEFAULT_REGION,
                    )
                    job.result()
                print(f"  Success: {table_name} is fully loaded to BigQuery!")
                successful_tables.append(table_name)
            except Exception as error:
                print(
                    f"  Error migrating table {table_name}: {_safe_error_category(error)}"
                )
                failed_tables.append(table_name)
            finally:
                if connection is not None:
                    with suppress(Exception):
                        connection.close()
                if temporary is not None:
                    try:
                        temporary.cleanup()
                    except Exception:
                        print(
                            "  Warning: temporary export cleanup failed; operator cleanup required."
                        )
        print(
            f"Migration Summary: {len(successful_tables)}/{len(TABLES_TO_MIGRATE)} tables successfully migrated."
        )
        if failed_tables:
            print(f"Failed tables: {failed_tables}")
            raise SystemExit(1)
    finally:
        if bq_client is not None:
            with suppress(Exception):
                bq_client.close()
        with suppress(Exception):
            pg_engine.dispose()


def main():
    parser = argparse.ArgumentParser(
        description="AdventureWorks ELT Pipeline: PostgreSQL -> BigQuery"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show preflight information without submitting any load jobs.",
    )
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="Explicitly confirm that writing to a production destination is intended.",
    )
    parser.add_argument(
        "--destination",
        type=str,
        default=None,
        help="Exact destination confirmation (e.g. quantum-echo-data-eng-prod.raw_adventureworks). "
        "Required for production writes.",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Disable interactive prompts. All confirmations must be provided via flags.",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Source batch rows (1 to {MAX_BATCH_SIZE}; default {DEFAULT_BATCH_SIZE}).",
    )

    args = parser.parse_args()

    interactive = not args.no_interactive and _is_interactive()

    try:
        run_elt_migration(
            dry_run=args.dry_run,
            confirm_production=args.confirm_production,
            destination=args.destination,
            interactive=interactive,
            batch_size=args.batch_size,
        )
    except (PipelineConfigurationError, PipelineConfirmationError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: {_safe_error_category(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
