"""Explicit one-time bootstrap. Never imported or exposed by the web application."""

import argparse
import os
from pathlib import Path
import psycopg2
from dotenv import load_dotenv


class BootstrapValidationError(ValueError):
    """Fixed, operator-facing validation messages without connection details."""


def connect_secure_database(url):
    """Require authenticated TLS before credentials or bootstrap SQL are sent."""
    options = {"connect_timeout": 8, "sslmode": "verify-full", "gssencmode": "disable"}
    root_certificate = os.environ.get("SUPABASE_DB_SSLROOTCERT")
    if root_certificate:
        options["sslrootcert"] = root_certificate
    connection = psycopg2.connect(url, **options)
    try:
        if not connection.info.ssl_in_use:
            raise BootstrapValidationError("Database connection requires TLS.")
    except Exception:
        connection.close()
        raise
    return connection


def bootstrap(connection, email):
    with connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(74112026)")
            cursor.execute("SELECT count(*) FROM public.platform_administrators")
            if cursor.fetchone()[0]:
                raise BootstrapValidationError(
                    "Platform administration is already bootstrapped."
                )
            cursor.execute(
                "SELECT id FROM auth.users WHERE lower(email)=lower(%s) AND email_confirmed_at IS NOT NULL",
                (email.strip(),),
            )
            row = cursor.fetchone()
            if not row:
                raise BootstrapValidationError(
                    "Sign up and confirm the initial administrator email first."
                )
            actor = row[0]
            cursor.execute(
                "INSERT INTO public.platform_administrators(user_id) VALUES (%s)",
                (actor,),
            )
            cursor.execute(
                "INSERT INTO public.workspaces(name,purpose,responsible_team) VALUES (%s,%s,%s) RETURNING id",
                (
                    "AdventureWorks Analytics",
                    "Sales Performance, Customer Intelligence & Pipeline Monitoring",
                    "Data & Analytics Team",
                ),
            )
            workspace = cursor.fetchone()[0]
            cursor.execute(
                "UPDATE public.workspaces SET registration_default=true WHERE id=%s AND NOT EXISTS (SELECT 1 FROM public.workspaces WHERE registration_default)",
                (workspace,),
            )
            cursor.execute(
                "INSERT INTO public.workspace_memberships(workspace_id,user_id,role) VALUES (%s,%s,'owner')",
                (workspace, actor),
            )
            cursor.execute(
                "INSERT INTO public.governance_audit_events(workspace_id,actor_id,action,target_id) VALUES (%s,%s,'platform_bootstrapped',%s)",
                (workspace, actor, actor),
            )
            return workspace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        parser.error("Set SUPABASE_DB_URL privately before running bootstrap.")
    try:
        connection = connect_secure_database(url)
        try:
            workspace = bootstrap(connection, args.email)
        finally:
            connection.close()
        print(f"Bootstrap complete. Initial workspace: {workspace}")
    except (psycopg2.Error, ValueError) as error:
        # Never print database connection errors, which may contain credential URLs.
        parser.exit(
            1,
            (
                str(error) + "\n"
                if isinstance(error, BootstrapValidationError)
                else "Database bootstrap failed. Check connectivity and migrations.\n"
            ),
        )


if __name__ == "__main__":
    main()
