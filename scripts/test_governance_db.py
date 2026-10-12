"""Run isolated PostgreSQL RLS and concurrency tests. Requires local Docker."""

import concurrent.futures
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_tests(container):
    def sql(content, check=True):
        return subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                container,
                "psql",
                "-h",
                "127.0.0.1",
                "-U",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
            ],
            input=content,
            text=True,
            capture_output=True,
            check=check,
        )

    sql((ROOT / "supabase/tests/auth_stub.sql").read_text())
    migrations = sorted((ROOT / "supabase/migrations").glob("*.sql"))
    for migration in migrations[:3]:
        sql(migration.read_text())
    sql((ROOT / "supabase/tests/governance.sql").read_text())
    sql((ROOT / "supabase/tests/registration.sql").read_text())
    sql(
        "insert into auth.users(id,email,email_confirmed_at) values('a0000000-0000-0000-0000-000000000099','legacy-pending@example.test',now()); set role authenticated; select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000002',false); select public.approve_workspace_email('10000000-0000-0000-0000-000000000001','legacy-pending@example.test','viewer'); reset role;"
    )
    for migration in migrations[3:]:
        sql(migration.read_text())
    sql((ROOT / "supabase/tests/access_requests.sql").read_text())
    sql((ROOT / "supabase/tests/password_lockout.sql").read_text())

    # Separate connections exercise the row lock under simultaneous attempts.
    def failed_password(_):
        return sql(
            'set role supabase_auth_admin; select public.hook_password_lockout(\'{"user_id":"b0000000-0000-0000-0000-000000000001","valid":false}\');'
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(failed_password, range(8)))
    result = sql(
        "select failed_attempts=5 and locked_until>now() from governance_private.password_login_state where user_id='b0000000-0000-0000-0000-000000000001'; select count(*) from governance_private.password_lockout_events where action='password_locked';"
    )
    assert "\n t\n" in result.stdout and "\n     2\n" in result.stdout, result.stdout

    sql(
        "insert into auth.users(id,email,email_confirmed_at) values('a0000000-0000-0000-0000-000000000010','race@example.test',now());"
    )

    def review(actor):
        return sql(
            f"begin; set role authenticated; select set_config('request.jwt.claim.sub','{actor}',true); select public.review_workspace_request('10000000-0000-0000-0000-000000000001',(select id from public.workspace_access_requests where user_id='a0000000-0000-0000-0000-000000000010' and status='pending'),'approved','viewer',''); commit;",
            check=False,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        decisions = list(
            executor.map(
                review,
                [
                    "00000000-0000-0000-0000-000000000002",
                    "00000000-0000-0000-0000-000000000003",
                ],
            )
        )
    assert sorted(r.returncode == 0 for r in decisions) == [False, True]
    result = sql(
        "select count(*) from public.governance_audit_events where target_id='a0000000-0000-0000-0000-000000000010' and action='access_approved';"
    )
    assert "\n     1\n" in result.stdout, result.stdout

    def demote(actor):
        return sql(
            f"begin; set role authenticated; select set_config('request.jwt.claim.sub','{actor}',true); select public.change_workspace_member('10000000-0000-0000-0000-000000000001','{actor}','viewer',true); select pg_sleep(0.3); commit;",
            check=False,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                demote,
                [
                    "00000000-0000-0000-0000-000000000002",
                    "00000000-0000-0000-0000-000000000007",
                ],
            )
        )
    assert sorted(r.returncode == 0 for r in results) == [False, True], [
        (r.stdout, r.stderr) for r in results
    ]
    result = sql(
        "select count(*) from public.workspace_memberships where workspace_id='10000000-0000-0000-0000-000000000001' and active and role='owner';"
    )
    assert "\n     1\n" in result.stdout, result.stdout
    print(
        "Governance, RLS, role boundaries, request approvals, password lockout/expiry/recovery, concurrent password failures, and concurrent last-owner tests passed."
    )


def main():
    container = "aw-governance-test-" + uuid.uuid4().hex[:8]
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            container,
            "--network",
            "none",
            "-e",
            "POSTGRES_PASSWORD=local-test-only",
            "postgres:17",
        ],
        check=True,
        capture_output=True,
    )
    try:
        for _ in range(60):
            if (
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        container,
                        "pg_isready",
                        "-h",
                        "127.0.0.1",
                        "-U",
                        "postgres",
                    ],
                    capture_output=True,
                ).returncode
                == 0
            ):
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("Isolated PostgreSQL did not become ready.")
        run_tests(container)
    except subprocess.CalledProcessError as error:
        print(error.stderr or error.stdout)
        raise
    finally:
        subprocess.run(["docker", "stop", container], check=True, capture_output=True)


if __name__ == "__main__":
    main()
