import argparse
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv
import sqlalchemy as sa
import pandas as pd
from google.cloud import bigquery
from db_connector import get_postgres_engine

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


def run_elt_migration(
    dry_run=False, confirm_production=False, destination=None, interactive=None
):
    """Run the ELT migration with safeguards.

    Args:
        dry_run: If True, print preflight info and exit without executing loads.
        confirm_production: Explicit production confirmation flag.
        destination: Exact destination confirmation string.
        interactive: Whether to allow interactive prompts.
                     If None, auto-detected from stdin.

    Raises:
        PipelineConfigurationError: on missing or contradictory configuration.
        PipelineConfirmationError: if production confirmation requirements are not met.
    """
    _validate_options(dry_run, confirm_production, destination, interactive)
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
    bq_client = bigquery.Client(project=project_id)

    print(f"\nStarting cloud-native database migration to {DEFAULT_REGION}...")

    successful_tables = []
    failed_tables = []

    for table_name in TABLES_TO_MIGRATE:
        try:
            print(f"Processing table: {table_name}...")

            with pg_engine.connect() as pg_conn:
                query = sa.text(f"SELECT * FROM public.{table_name}")  # nosec B608
                query_result = pg_conn.execute(query).fetchall()
                records = [dict(row._mapping) for row in query_result]

            if records:
                df = pd.DataFrame(records)

                for col in df.columns:
                    if df[col].apply(lambda x: x.__class__.__name__ == "Decimal").any():
                        df[col] = df[col].astype(float)

                table_ref = f"{project_id}.{dataset_id}.{table_name}"

                job_config = bigquery.LoadJobConfig(
                    write_disposition=WRITE_DISPOSITION,
                )

                print(
                    f"  -> Streaming {len(records)} rows directly to BigQuery via cloud APIs..."
                )
                job = bq_client.load_table_from_dataframe(
                    df, table_ref, job_config=job_config, location=DEFAULT_REGION
                )
                job.result()

                print(f"  Success: {table_name} is fully loaded to BigQuery!")
                successful_tables.append(table_name)
            else:
                print(f"  Skipping {table_name}: Table is empty.")

        except Exception as e:
            print(f"  Error migrating table {table_name}: {_safe_error_category(e)}")
            failed_tables.append(table_name)
            continue

    print(
        f"Migration Summary: {len(successful_tables)}/{len(TABLES_TO_MIGRATE)} tables successfully migrated."
    )
    if failed_tables:
        print(f"Failed tables: {failed_tables}")
        raise SystemExit(1)


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

    args = parser.parse_args()

    interactive = not args.no_interactive and _is_interactive()

    try:
        run_elt_migration(
            dry_run=args.dry_run,
            confirm_production=args.confirm_production,
            destination=args.destination,
            interactive=interactive,
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
