# Bootstrap database credentials

`SUPABASE_DB_URL` is a privileged PostgreSQL connection secret for the standalone
`scripts/bootstrap_workspace.py` CLI. Keep it out of the Dash/Flask service,
browser configuration, frontend bundle, container builds, application deployment
variables, logs, and version control. It is not a Supabase public API key.

## Injection and storage

Use an approved secret manager to inject the URL into an explicitly authorized,
one-time operator process. A private root `.env` is supported locally; the CLI
loads it with `override=False`, so runtime environment variables take precedence.
Restrict file permissions and retain it only while needed. Ignoring `.env` and
blocking credential filenames in hooks reduces accidental commits; it does not
prove credentials were never exposed. Do not paste the URL into chat, shell
commands/history, process arguments, issue reports, or tracked configuration.
Disable shell tracing and command/environment logging for the operator job.
Never run bootstrap through the web service or to test a rotated password.

## TLS and server identity

Supply an explicit TCP hostname in the URL (or `PGHOST`); missing hosts and
Unix-socket paths are rejected before connecting, because libpq ignores SSL
options on Unix sockets. The CLI supplies `sslmode=verify-full` and `gssencmode=disable` as connection
keyword arguments. They override weaker URL settings and environment defaults,
so libpq must verify the server certificate chain and hostname before database
password authentication. It then checks `connection.info.ssl_in_use` before any
bootstrap SQL. A false result closes the connection and fails. TLS encryption
alone does not establish server identity; `sslmode=require` is insufficient for
this contract. See [libpq SSL documentation](https://www.postgresql.org/docs/current/libpq-ssl.html)
and [Psycopg connection options](https://www.psycopg.org/docs/module.html).

Provision the approved CA certificate for the exact direct/pooler endpoint you
use. Set `SUPABASE_DB_SSLROOTCERT` to its protected local PEM path, or configure
libpq's `sslrootcert` through the URL, `PGSSLROOTCERT`, or its standard
`~/.postgresql/root.crt` location. The dedicated variable overrides those other
root-certificate settings; runtime values take precedence over `.env`. Trust
files are certificates, not passwords, but their integrity matters. Do not
replace a failed certificate/hostname check with weaker SSL settings. Connection
attempts have an eight-second timeout; connection failure messages are generic
and never print driver exceptions or URLs. Fixed bootstrap validation messages
remain operator-visible.

## Required privileges and safeguards

Supabase's hosted `postgres` role is privileged but **not a true superuser**.
Check the actual role, ownership, policies, and inherited privileges before
using it; do not assume an arbitrary role can read `auth.users` or bypass RLS.
[Supabase role documentation](https://supabase.com/docs/guides/database/postgres/roles-superuser).

The bootstrap transaction needs database CONNECT, schema USAGE on `auth` and
`public`, and privileges for these operations (column grants can be narrower):

| Object                           | Required operations                                                                                              |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `auth.users`                     | SELECT `id`, `email`, `email_confirmed_at`                                                                       |
| `public.platform_administrators` | SELECT for count; INSERT `user_id`                                                                               |
| `public.workspaces`              | INSERT `name`, `purpose`, `responsible_team`; SELECT `id`, `registration_default`; UPDATE `registration_default` |
| `public.workspace_memberships`   | INSERT `workspace_id`, `user_id`, `role`                                                                         |
| `public.governance_audit_events` | INSERT `workspace_id`, `actor_id`, `action`, `target_id`                                                         |

Account for sequence USAGE and function EXECUTE when defaults/triggers require
them, including EXECUTE on `pg_advisory_xact_lock(bigint)`. RLS must permit each
operation through the actual role's policies, legitimate ownership, or a
separately approved BYPASSRLS capability. FORCE ROW LEVEL SECURITY affects table
owners. `pg_read_all_data` and `pg_write_all_data` do **not** bypass RLS.
[PostgreSQL predefined roles](https://www.postgresql.org/docs/current/predefined-roles.html).
No grants, policies, or role changes are automated by this remediation.

Apply the repository migrations first. Bootstrap holds an advisory transaction
lock, refuses a second bootstrap, requires an existing confirmed-email user,
and creates administrator, workspace, owner membership, and audit record in one
transaction. Database errors roll back and the CLI closes the connection.

## Rotation runbook — operator execution pending

1. Prepare an impact inventory without revealing secrets. For tracked code,
   use this filename-only search (it does not read ignored `.env` files):

   ```sh
   git grep -l SUPABASE_DB_URL -- '*.py' '*.md' '*.yml' '*.yaml' Dockerfile
   ```

   Separately inventory authorized secret-manager references and operator jobs
   through their management interfaces, without dumping secret values. Confirm
   the connected role and direct/pooler consumers; a shared `postgres` password
   rotation may affect migrations, backups, and external jobs. A code search
   cannot establish all operational consumers.

2. Have the authorized DBA review privileges and role attributes. The following
   read-only query uses the correct information-schema column names and reports
   grants visible to the connected operator, not a complete effective/RLS audit:

   ```sql
   SELECT table_schema, table_name, privilege_type
   FROM information_schema.role_table_grants
   WHERE grantee = current_user;
   ```

3. Prepare the replacement secret, trusted CA, consumer update plan, maintenance
   window, and recovery access in approved management tools. Obtain separate
   explicit production authorization before changing the database password or
   roles. Do not put password SQL or connection URLs into command arguments.

4. Execute the authorized rotation using the provider/DBA's secure password
   reset workflow; update approved consumers through secret-manager injection.
   For a single role password, reset invalidates the old password for new
   connections immediately: there is no assumption of overlapping validity.
   Coordinate this cutover before resetting. Existing sessions may survive;
   their termination requires an explicitly approved operational decision.

5. Verify connectivity from an authorized operator environment using only
   `SELECT 1`, not bootstrap. Inject the URL and trust configuration privately,
   then use this script from the repository root. Importing the CLI does not
   load `.env` or run bootstrap; the snippet requires runtime injection:

   ```sh
   uv run python - <<'PY'
   import os
   import psycopg2
   from scripts.bootstrap_workspace import connect_secure_database

   try:
       connection = connect_secure_database(os.environ['SUPABASE_DB_URL'])
       try:
           with connection:
               with connection.cursor() as cursor:
                   cursor.execute('SELECT 1')
                   if cursor.fetchone() != (1,):
                       raise ValueError('Unexpected connectivity result')
       finally:
           connection.close()
   except (KeyError, ValueError, psycopg2.Error):
       raise SystemExit('Connectivity verification failed; check private configuration.')
   print('Verified TLS connectivity OK')
   PY
   ```

   The helper enforces certificate/hostname verification and negotiated TLS.
   Successful connectivity does not prove bootstrap table privileges or RLS
   correctness. Never log raw exceptions, DSNs, or environment contents.

6. Confirm all inventoried consumers, revoke obsolete credentials/roles only
   when separately authorized, and review operational audit records. Remove
   obsolete secret-manager versions according to retention policy and private
   local copies/backups/editor recovery files through secure management tools.
   Inspect and remove any accidentally retained shell history privately; do
   not print history or `.env` values into a shared terminal/report.

If cutover fails, pause affected jobs and use approved provider/DBA recovery
access to set a fresh valid password and update consumers. Restoring an older
secret-manager value **does not** restore the database password after reset.
Do not rerun bootstrap or drop/recreate roles as a connectivity recovery step.
Record verification and authorization evidence without secret values.

Repository code and documentation are complete. **Production credential
rotation remains pending** separate authorization and operator evidence. No
production connections, bootstrap execution, password changes, or grants were
performed as part of this remediation.
