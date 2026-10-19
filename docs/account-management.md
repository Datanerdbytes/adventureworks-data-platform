# Account authentication cutover

Local implementation prepared on 2026-10-19 using the
[supabase-account-management skill](/Users/roelsomido/.codex/skills/supabase-account-management/SKILL.md).
Hosted status verified on 2026-10-19: safety migrations `202610190001`–
`202610190003` are installed and both guard readiness functions return true.
The confirmed `datanerdbytes@gmail.com` account has the protected owner/admin role.
Supabase does not allow the operator role to index its managed `auth.users` table;
owner uniqueness therefore uses the private `public.qe_protected_owner` singleton
registry, written transactionally by the guard. All 20 isolated SQL tests pass.
Migration `202610190004`, password-lockout activation, legacy Auth-hook changes,
provider/email configuration and live application deployment remain separate steps.
No account access was changed as a test of these migrations.

## Access policy

Email-first signup requires confirmation. Every confirmed, active account can
access the shared AdventureWorks analytics application; workspace approval and
membership no longer authorize access. Existing verified accounts, including
formerly pending or revoked workspace members, can sign in unless their **account**
is suspended. Review account suspensions before cutover if those users should
remain blocked. Old workspace Owner/Admin/Platform Admin roles do not confer the
new administrator role.

The server verifies tokens with Supabase Auth on every protected request. Only
server-controlled `app_metadata.qe_role = "admin"` grants administration;
`qe_owner = true` marks the single protected owner. `qe_suspended = true` or an
active provider ban blocks access, including existing app sessions. User-editable
metadata and browser state never grant privileges. The protected owner is
`datanerdbytes@gmail.com`, subject to verification by the operator bootstrap.

`/admin/users` provides a bounded directory (25 accounts per provider page, ten
visible grid rows), role grant/revoke and suspend/restore actions. Admins cannot
change themselves or the owner; demote an admin before suspension. The owner can
delete a suspended non-admin after typing its current email. A transactional
Auth-table trigger checks the current row at deletion to prevent restoration or
promotion races. Storage ownership and foreign-key failures remain blocking;
the app never deletes files or changes constraints to force deletion. Refresh
before retrying an uncertain deletion. A deleted email can register again.

The old `/workspace/admin*`, `/auth/registration` and `/auth/workspace` endpoints
are retired. `/workspace` is a shared analytics overview; synthetic sections
remain labeled. Historical workspace records and audit events are retained.

## Runtime settings

Keep the existing public URL/key, exact `AUTH_APP_ORIGIN`, stable
`FLASK_SECRET_KEY`, production Redis limiter and trusted proxy configuration.
Browser configuration exposes only the public URL/key, configured OAuth providers
and password lockout feature flag.

Add `SUPABASE_SERVICE_ROLE_KEY` as a server-only runtime secret for account
management and password-attempt RPCs. Never put it in the public key setting,
frontend build, browser stores or logs. Do not add `SUPABASE_DB_URL` to the web
service. Runtime environment takes precedence over the local `.env`.

Enable `AUTH_PASSWORD_LOCKOUT_ENABLED=true` after installing and verifying the
lockout migration and service credential. With the flag true, password login uses
`/auth/password`; failures of shared storage fail closed. Five explicit invalid
passwords within 15 minutes lock application access for 15 minutes. One bounded
attempt lease serializes submissions; stale attempts cannot settle newer leases.
A valid password before the threshold or an actual password-hash change clears
failures. Recovery email requests do not unlock an account. Provider timeouts,
unconfirmed email, bans and throttling do not count as bad passwords.

With the flag false (default), password login uses Supabase directly and the new
shared lockout is **inactive**. There is no automatic fallback on failure. Direct
Supabase password calls are outside the app's attempt counter; an active app lock
still blocks application access. This is not a provider-wide ban. Review and
configure retention of inactive counters separately; no cleanup job is installed.

## Operator rollout (separate authorization)

1. Review the access-policy change and historical account/member states. Take the
   usual database backup and plan a maintenance window; old application revisions
   depend on the governance grants being retired.
2. Apply pending migrations in filename order, including `202610190001` through
   `202610190004`. The first three add shared lockout, deletion protection, owner
   protection and administrator/suspension invariants. The fourth stops approval
   queueing and revokes old workspace RPC/table access without deleting history.
   Existing historical migrations remain required on a fresh database.
3. In Supabase Auth, disable the old `hook_password_lockout` password-verification
   hook if it was enabled. Its older counter is independent of the new gateway.
   Keeping both active can produce conflicting locks. Do not delete historical
   counter data as part of this cutover.
4. Verify email confirmation, the minimum 12-character signup/recovery password
   policy, SMTP, Site URL and explicit allowed `<origin>/auth/callback` and
   `<origin>/auth/recovery?step=update` redirects. Install
   `supabase/templates/recovery.html`, which uses `{{ .ConfirmationURL }}` for
   PKCE. Reset links must be opened in the browser that requested them. Previously
   issued fragment-token reset links must be replaced by a new reset email.
   OAuth providers remain separately configured and enabled through
   `AUTH_OAUTH_PROVIDERS`; new accounts still register with email first.
5. Configure the server service-role secret and production Redis. Run the owner
   bootstrap dry run, then apply only with separate operator authorization:

   ```sh
   uv run --locked python scripts/bootstrap_account_owner.py --email datanerdbytes@gmail.com
   uv run --locked python scripts/bootstrap_account_owner.py --email datanerdbytes@gmail.com --apply
   ```

   The account must already exist, have confirmed email and be active. Bootstrap
   will refuse a different existing owner. The private singleton owner registry prevents
   parallel bootstrap commands from creating two owners. No owner is assigned on
   application startup; existing workspace roles are not migrated implicitly.

6. Deploy the new built image with lockout enabled, verify guard readiness and
   account flows, then route traffic. Configure service identity access to the
   runtime secret using your deployment process. A secret update alone does not
   deploy the code. All workers must use the same settings.

Rollback needs a coordinated old-image deployment and restoration of historical
workspace grants/approval trigger. Do not simply route traffic to an older image
after migration `202610190004`. Review new suspended accounts and new open-signup
users during rollback. Never drop the Auth guards just to make a write succeed.

## Recovery and request boundaries

Recovery uses an isolated, in-memory Supabase session and unique storage/channel
key. Only the one-time PKCE verifier is shared across pages. The exchanged flow
must be recovery; updates are bound to the recovered user ID. Cached login
sessions and arbitrary URL fragment tokens cannot initialize recovery. Identity
changes invalidate the form. Success clears application/recovery sessions, asks
Supabase to revoke refresh sessions and clears the normal local browser session,
then requests a fresh sign-in. Issued stateless JWTs in other services have their
own expiry/revocation policy. Recovery does not clear administrator suspension.

Cookie-bound CSRF and exact Origin checks cover session/password endpoints, all
Dash writes and administrator API mutations. Rejected writes are not replayed.
The server guard still runs before callbacks and warehouse loaders. Protected
responses remain private/no-store; access cookies remain HttpOnly, SameSite=Lax
and Secure outside explicit HTTP localhost development. No user tokens or raw
Auth records are placed in Dash stores.

## Local checks

```sh
uv run --locked python scripts/pre_commit_checks.py python-tests
npm ci
npm run build:auth
npm run test:auth
```

`supabase/tests/account-management.test.mjs` runs the first three migrations in
an isolated PGlite database with synthetic `auth.users`, never hosted Supabase:

```sh
QE_PGLITE_MODULE=/absolute/path/to/pglite/dist/index.js node --test supabase/tests/account-management.test.mjs
```

The SQL suite covers lockout thresholds, expiry, lease races, client privilege
denial, hash-change unlocking, deletion races and administrator/suspension
invariants. The fourth migration is also exercised against synthetic historical
objects by the cutover test. Install PGlite in a disposable test environment; it
is not a runtime dependency. Local tests do not prove hosted migrations, email
delivery, live redirects, real account changes or deployed runtime behavior.

The legacy database runner, `scripts/test_governance_db.py`, uses the shared Auth
stub and runs governance permissions and separate-connection concurrency checks
before retirement migration `202610190004`. It then applies retirement and history
separation and verifies revoked client access, active safety guards and preserved
legacy row counts. Run it against its disposable Docker PostgreSQL container:

```sh
uv run --locked python scripts/test_governance_db.py
```

The history SQL suite also exercises this migration/legacy-check sequence with
the shared stub in PGlite; it does not replace Docker's concurrent connections.

Supabase API contracts checked against the official
[PKCE guide](https://supabase.com/docs/guides/auth/sessions/pkce-flow),
[admin metadata update](https://supabase.com/docs/reference/javascript/auth-admin-updateuserbyid),
[account deletion API](https://supabase.com/docs/reference/javascript/auth-admin-deleteuser)
and [Auth error codes](https://supabase.com/docs/guides/auth/debugging/error-codes).

## Optional legacy history separation

A separate migration, `202610190005_legacy_account_history.sql`, is installed
to preserve legacy workspace/audit records while allowing eligible Auth-account
deletion. It was applied to hosted Supabase with user authorization on 2026-10-19; preservation checks passed and no account was deleted. See
[legacy account history](legacy-account-history.md) for its exact retention policy,
independent rollout and isolated tests. Do not apply workspace cutover 0004
implicitly when installing this optional migration.
