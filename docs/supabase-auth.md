# Supabase Authentication and Workspace Governance

The Dash/Flask server verifies each access token with Supabase Auth and reads
current workspace permissions before serving protected requests. No Basic Auth
fallback remains. Workspaces share the existing AdventureWorks BigQuery dataset;
workspace governance is not analytics tenant isolation.

## 1. Create and configure the dedicated project

Create a new Supabase project in your organization. Keep its database password
private. Copy the project URL and **public anon or publishable key** into the
variables in `.env.example`, using the root `.env` locally. Runtime environment
values take precedence. Do not put a secret or service-role key in a public-key
variable. The running application needs no privileged Supabase key.

Use `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` for the public key. The legacy
`NEXT_PUBLIC_SUPABASE_ANON_KEY` name remains supported; the publishable setting
takes precedence when both are supplied.

Set `AUTH_APP_ORIGIN` to the exact origin used in your browser, for example
`http://127.0.0.1:8050`; `localhost` is a different origin. Hosted deployments
require HTTPS. Generate a stable `FLASK_SECRET_KEY` privately and configure it
for every worker. It signs only the selected workspace ID; access tokens are in
a separate HttpOnly cookie and refresh tokens remain managed by Supabase JS.

In Supabase Auth:

- Enable email/password and email confirmation. Use at least a 12-character
  password policy. Configure SMTP for production confirmation/recovery delivery.
- Set Site URL to the app origin. Add exact allowed redirects for
  `<origin>/auth/callback`, `<origin>/auth/recovery?step=update`, and callback
  redirects with allowed `next` query strings. Avoid production wildcard origins.
- Configure Google and GitHub independently. Their provider redirect URI is
  `https://<project-ref>.supabase.co/auth/v1/callback`; the app redirect is
  `<origin>/auth/callback`. They are not interchangeable.
- Only after each provider works, add its name to `AUTH_OAUTH_PROVIDERS`, e.g.
  `google,github`. A rendered button is not proof of provider configuration.
- OAuth requires a verified email. Accounts without a usable confirmed email
  cannot access the workspace; use confirmed email/password instead.

OAuth and same-browser confirmation/recovery use PKCE. For email links that may
be opened on another device, configure templates to use Supabase token hashes:

```
Confirmation: {{ .SiteURL }}/auth/callback?token_hash={{ .TokenHash }}&type=signup
Recovery: {{ .SiteURL }}/auth/recovery?token_hash={{ .TokenHash }}&type=recovery&step=update
```

The browser verifies these one-time hashes through Supabase and removes them
from the URL before continuing. Never log callback query strings, passwords,
cookies, bearer tokens, or bootstrap database URLs in proxies or application logs.
Supabase controls Auth-user lifecycle; the app does not create passwords, send
invitations, or delete Supabase accounts.

## 2. Database setup and one-time bootstrap

First run the isolated tests below. Then apply the files in
`supabase/migrations/` in filename order through SQL Editor or your migration
tool. Apply each migration once and record it in your deployment process.
The first migration creates governance objects. The second adds a narrowly
scoped BEFORE INSERT trigger to `auth.users` that rejects new accounts unless
Supabase's server-managed `raw_app_meta_data.provider` is `email`. Existing
accounts and identity linking remain unaffected. The third requires an existing
confirmed Auth account before an Owner/Admin can approve an email. This is
checked inside the authorized transactional RPC; unknown and unverified emails
are rejected without creating an approval. The fourth migration introduces verified access requests and immediate, transactional membership approval. No migration touches BigQuery.
Do not re-run applied migrations on a populated project.
Migration 005 is prepared for password lockout and is **not applied or active
in the configured hosted project**. Its activation requirements are below.

The registration flow is email signup → email verification → workspace approval
→ sign-in. `/signup` offers email/password only. Supabase's hosted email
verification endpoint confirms the account before redirecting. Registration
redirects with `registration=1&code=...` return to sign-in without exchanging
that code or creating an application session, so opening the email in another
browser does not require the signup browser's PKCE verifier. OAuth and password
recovery codes still use PKCE. Direct `token_hash` signup links are verified via
`verifyOtp` and their temporary registration session is signed out.
Confirmation itself queues the request, even if the browser does not return.
The notice is informational; the server independently verifies confirmation and
membership on every sign-in. An already-used email link may report an expired
token: check the approval queue before repeating signup or resending email.
Google/GitHub are available on `/login` for existing accounts with the same
verified email; they cannot create a new account, including through direct
Supabase OAuth calls. Supabase automatically links matching verified email
identities; provider email visibility/verification must be configured correctly.
Unapproved sign-in clears application cookies and returns to sign-in with an
approval-pending message. Browser-managed Auth tokens alone never grant analytics
access. Unknown email/password login keeps Supabase's generic credentials error
to avoid exposing which emails are registered; the page links to signup.

Set
`SUPABASE_DB_URL` privately to the project's privileged Postgres connection URL
(with an approved trusted CA for certificate and hostname verification), then run:

```sh
uv run python scripts/bootstrap_workspace.py --email your-confirmed-email
```

Bootstrap uses one transaction and a lock, refuses a second bootstrap, and
creates an audit event. It grants that confirmed user Platform Admin and Owner
of AdventureWorks Analytics. The workspace's responsible team is Data & Analytics
Team; its purpose is Sales Performance, Customer Intelligence & Pipeline
Monitoring. The database URL is a CLI-only secret and must not enter the app's
browser configuration or container runtime unless explicitly needed for an
independent administration job. Never expose bootstrap as a web endpoint.

See [bootstrap credential handling](bootstrap-credentials.md) for enforced
verified TLS, trust configuration, privileges, and the operator rotation runbook.
Production credential rotation remains pending separate authorization and evidence.

## 3. Provisioning and permissions

Open `/workspace/admin` after sign-in:

- Platform Admin creates a workspace and assigns a **confirmed** initial owner.
  That owner may sign up before provisioning, remaining access-pending until then.
- Owner edits details and manages Owner, Admin, and Viewer membership.
- Admin approves and manages Viewers only; cannot promote themselves or change
  higher roles.
- Viewer reads reports, tables, and exports. Viewers cannot open administration
  or use its mutation functions, even by forging callback requests.

Approving a verified access request creates or updates membership transactionally
for the confirmed Supabase user. No email invite is sent. Existing memberships
must be changed through the details modal on `/workspace/admin/members`, including
reactivating revoked access. Pending requests can be rejected. Membership
revocation takes effect at the next request,
even while a previously issued token remains valid. Removing the last active
owner is blocked under a workspace row lock, including simultaneous requests.

Approval requests fetch at most 50 records per page. The members page filters
across authorized workspaces, email, role, and access, returning ten memberships
per page. Selecting a member opens canonical details and permitted access edits.
Recent governance activity uses compact rows with actor emails and UTC times,
and an independent five-event pager across history. These read paths require
`202610150001_admin_directory_activity.sql`, applied to hosted project
`lcnsbwohtrxrtissvbzl` on 2026-10-15. Both read functions were verified with an
existing confirmed administrator identity; anonymous execution is denied.
Migration SHA-256: `991f0a5b49e20e25c84fed88cd72c5db24ae6f742ad9354e954c85c6a978d2f5`.
The hosted project had no Supabase CLI migration-history table at application
time; do not re-run this migration. The local authenticated app on port 8050
was restarted and its overview rendered live member counts and audit events.
Application deployment to hosted infrastructure remains separate.

The switcher lists authorized workspaces, validates the selection again on the server, and
reloads the shell. User roles and Supabase tokens are never stored in `dcc.Store`.
RLS and explicit grants protect direct database access. Governance mutations use
checked RPCs, enforce actor permissions inside Postgres, and write audit events
in the same transaction. Platform-admin records have no browser-write API.

## 4. Build and verify

```sh
uv sync
npm ci --ignore-scripts
npm run build:auth
npm run test:auth
uv run python -B -m unittest discover -s tests -v
python3 scripts/test_governance_db.py
uv run python my-dash-app/app.py
```

The database test uses a temporary PostgreSQL 17 Docker container with no network
ports, an Auth-schema fixture, real SQL migrations/RLS, and concurrent demotions.
It does not connect to any hosted project. Python tests mock provider/warehouse
calls. Browser verification with a mock provider does not establish that hosted
OAuth, email delivery, or your project's configuration works.

Before rollout, perform a real configured-project smoke test: email confirmation,
Google and GitHub sign-in, recovery, refresh/expiry, cross-tab sign-out, membership
revocation, role boundaries, workspace switching, exports, and outage states.
Do not enable production access until it passes. Do not replay rejected mutations.

Docker builds the tracked bundle from `auth_frontend/` in a Node stage and runs
Python/Gunicorn as a non-root user. Supply runtime environment settings; there
are no baked-in project keys. Never include `.env`, Google credentials, or
privileged database settings in the build context.

## Routes

Public auth screens: `/login`, `/signup`, `/auth/callback`, `/auth/recovery`,
`/auth/access-pending`. `/auth/config` returns public settings only.
`POST /auth/session` verifies an access token and synchronizes its HttpOnly cookie;
`DELETE /auth/session` clears it. `/auth/status` verifies current membership.
`POST /auth/workspace` validates an authorized workspace selection. All mutation
endpoints require exact Origin matching. Protected failures return 401, 403, or
503; browser navigation to unauthorized pages redirects to sign-in or access
pending. Authenticated `/` navigation redirects to `/dashboard`.

## Verified access-request queue

`workspace_access_requests` separates Pending/Approved/Rejected/Cancelled requests
from active/revoked memberships. Email is read from Auth, never trusted from a row
selection or profile metadata. Pending Approvals counts verified pending requests.
The administration grid lists Email, Requested At (UTC), and Status; selecting a
row enables an explicit Approve/Reject decision with a role and optional note.
An approval creates membership immediately, marks the request reviewed, and
writes an audit event under the workspace lock. Stale/concurrent decisions fail.
Admins grant Viewer only; Owners/Platform Admins can grant other roles. No
self-approval, cross-workspace decisions, or reactivation through a new request.

Each workspace has a registration code and enabled flag. `/signup?workspace=CODE`
resolves only that workspace; `/signup` resolves the one configured default.
These links route requests, not permissions. The metadata field carries only a
validated destination code; role/access always comes from database decisions.
The auth.users confirmation trigger queues verified email-first users. Its
security-definer function uses an empty search_path and no public execute grant.
Before initial bootstrap, generic signup remains available without a destination;
bootstrap sets the first workspace as the default. Additional workspaces receive
separate links exposed in their administration page. Disable registration using
`registration_enabled=false` via a privileged deployment/admin database operation;
no public endpoint can alter registration configuration.

Migration 004 preserves legacy approval history, grants already-approved verified
accounts their membership without waiting for sign-in, never reactivates revoked
members, and queues existing verified accounts without membership in the initial
default workspace. No email invitations or account deletion occur. The legacy
claim/revoke RPCs lose authenticated execution rights. Apply once after local tests.
The verified `request_workspace_access` RPC supports idempotent requests and later
reapplications; a self-service request/reapplication screen is not in this release.

See [Supabase's user-trigger guidance](https://supabase.com/docs/guides/auth/managing-user-data)
for the Auth trigger pattern. The isolated tests cover confirmation, RLS, forged
roles and workspaces, rejection, legacy preservation, and concurrent decisions.

## Password reset

Forgot Password opens `/auth/recovery`. Requesting a link uses Supabase Auth's
email recovery API and shows a generic response without disclosing whether an
email is registered. Supabase owns email delivery, rate limiting, link expiry,
and the credential change; workspace roles and memberships remain unchanged.

Allow `<AUTH_APP_ORIGIN>/auth/recovery?step=update` in Supabase Auth → URL
Configuration. The recovery-email sender uses an isolated, non-persistent
implicit-flow client so the default email template works across browsers.
Google/GitHub OAuth and existing authentication continue using PKCE. The recovery
page accepts only recovery fragments, passes their tokens directly to Supabase
JS, and removes them from the address bar before verification. Refresh tokens
never enter Flask cookies, Dash stores, logs, or requests to the application.
Existing PKCE recovery links and explicit recovery token-hash links are supported.

The new-password form is enabled only after Supabase establishes a valid recovery
session during that page load. Opening `?step=update` without a link, reloading a
consumed link, and invalid/expired links leave submission disabled with a link to
request another email. Require at least 12 characters and a matching confirmation;
Supabase also enforces its configured password policy. Success clears the app
cookie, signs out the local Auth session, and returns to sign-in. No automatic
analytics login or membership changes occur. Recovery auth events do not
synchronize application cookies.

If custom SMTP is configured later, `supabase/templates/recovery.html` is an
optional recovery email body using a one-time token hash in a URL fragment.
Supabase currently requires custom SMTP or an eligible plan to edit templates;
this is not required for the default recovery flow. Configure production SMTP
for reliable delivery to real users; default email delivery has service limits.
See [Supabase password recovery](https://supabase.com/docs/reference/javascript/auth-resetpasswordforemail)
and [email templates](https://supabase.com/docs/guides/auth/auth-email-templates).

Offline tests exercise recovery links, missing/expired links, password validation,
and server route protection. Complete a real email delivery and password change
smoke test with a disposable account before rollout; the person testing must
enter and submit their new password themselves.

## Password lockout (prepared; activation pending)

`202610120005_password_lockout.sql` implements full enforcement through Supabase
Auth's Password Verification Attempt hook. The configured Free project cannot
activate that hook: Supabase currently provides it on Teams and Enterprise.
Do not claim lockout is enabled merely because the migration exists or was
applied. No browser/app-only fallback is installed.

Policy: five consecutive incorrect password attempts within a 15-minute window
lock password sign-in for 15 minutes from the fifth failure. Success before the
threshold clears the failure count. During lockout, even a correct password is
rejected; attempts do not extend expiry. A valid sign-in is accepted after expiry,
and the next failed attempt starts a fresh window. Failed passwords retain the
generic credentials error to avoid exposing which email addresses exist. A valid
password during lockout receives an inline wait/reset message through the existing
authentication error display.

Counters are keyed by Supabase user ID, never email/client storage/IP alone.
The transactional row lock handles concurrent attempts. Only `supabase_auth_admin`
can execute the hook and update the private state through its explicit grants and
RLS policies. Browser roles cannot read/reset counters or submit forged outcomes.
The hook records no passwords, tokens, email addresses, or IP addresses. Its
private event ledger records only user ID, timestamp, and lock/reset action.

The hook explicitly sets `should_logout_user=false`; malicious failed attempts
cannot terminate existing sessions. OAuth and email recovery are not blocked by
this password-only policy. An actual change to Auth's `encrypted_password` clears
the counter and lock transactionally, so successful recovery permits immediate
password sign-in. Editable profile metadata cannot clear the lock. Temporary
lockout still allows someone who knows an account email to disrupt password
sign-in for the fixed duration; retaining Supabase rate limits helps limit abuse.

Activation, when a supported plan is available:

1. Run the isolated tests: `python scripts/test_governance_db.py`.
2. Apply migration 005 once using the privileged migration connection.
3. In Supabase Authentication → Auth Hooks, enable Password Verification Attempt
   as a Postgres hook and select `public.hook_password_lockout`.
4. Verify with a designated disposable confirmed account: five wrong passwords,
   correct password rejected while locked, recovery clears lock, and expiration
   restores access. Check direct Supabase Auth calls as well as the app.
5. If activation causes unexpected failures, disable this hook in Auth Hooks.
   Preserve the migration and private audit data while diagnosing the issue.

For local Supabase, add this to its generated `config.toml`:

```toml
[auth.hook.password_verification_attempt]
enabled = true
uri = "pg-functions://postgres/public/hook_password_lockout"
```

SQL tests cover thresholds, correct-password rejection, expiry, window reset,
recovery unlocking, metadata tampering, role restrictions, malformed events, and
eight concurrent failures. These exercise Postgres policy logic, not a configured
hosted Auth hook. Complete the Auth-service integration test before enabling it
for real users.

See [hook availability and permissions](https://supabase.com/docs/guides/auth/auth-hooks)
and [password-verification hook](https://supabase.com/docs/guides/auth/auth-hooks/password-verification-hook).
