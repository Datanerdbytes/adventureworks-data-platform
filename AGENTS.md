# Current authentication override — 2026-10-19

The user explicitly replaced workspace approval with the supabase-account-management
skill's single protected owner/admin model. This section supersedes conflicting
workspace/auth descriptions below; analytics and production safety rules remain.
See [account management](docs/account-management.md) for the current contract and
separately authorized hosted cutover. Confirmed active emails access shared reports;
server-controlled `qe_role`, `qe_owner`, and `qe_suspended` govern account access.
`/admin/users` replaces `/workspace/admin*`; workspace switching/approval endpoints
and callbacks are retired. Historical governance data/migrations are retained.
The designated owner is `datanerdbytes@gmail.com`; only the explicit bootstrap CLI
may assign that role after verification. No hosted owner assignment is implied.
Preserve existing Origin, cookie-bound CSRF, shared Redis rate limiting, session
startup gating and warehouse boundaries. Account management requires a server-only
service-role secret. New shared lockout requires its migration and explicit flag;
failure must never fall back to direct login when enabled. Recovery uses isolated
PKCE state and a bound identity; old fragment reset links require a fresh email.
Run offline Python/auth tests and build tracked auth assets after source changes.
Do not apply hosted migrations, change real accounts or deploy without authorization.

# Agent Context & Rules

Repository state reviewed: **2026-10-15**. This guide describes checked-in behavior; production configuration and deployment must be verified separately.

## 1. Project Overview

- **Project Name:** AdventureWorks Analytics (Data Analytics Dashboard)
- **Core Purpose:** An authenticated, workspace-governed Dash analytics application with BigQuery-backed sales reports, PostgreSQL → BigQuery ingestion, and dbt transformations. Dashboard activity and pipeline monitoring currently include synthetic fixtures; do not describe them as live telemetry.
- **Target Audience:** Internal business analysts, data engineers, and stakeholders.

## 2. Tech Stack & Environment

- **Language:** Python 3.12 locally and in Docker; `pyproject.toml` requires Python >=3.12
- **Python Dependencies:** Root `pyproject.toml` and `uv.lock`, managed with uv
- **Core Framework:** Plotly Dash
- **Underlying Engine:** Flask, including Flask-Caching
- **Authentication:** Supabase Auth with `@supabase/supabase-js`, OAuth PKCE, and Flask server-side authorization
- **Frontend Build:** Node.js 22+, npm, and esbuild for the authentication bundle
- **Data Engine:** Google BigQuery via Application Default Credentials (ADC); dbt produces transformation artifacts, while the current monitoring UI uses fixtures
- **Data Libraries:** `google-cloud-bigquery`, `pandas`, `pandas-gbq`, `pyarrow`, `json`
- **Caching Framework:** Flask-Caching with FileSystemCache for warehouse results; Redis is required separately for production authentication rate limiting
- **Styling:** Dash component libraries and modular CSS
- **Code Quality:** Pinned Ruff, Black, mypy, Bandit, detect-secrets, pip-audit, and pre-commit; Prettier for CSS, JavaScript, JSON, YAML, and Markdown

## 3. Architecture & File Structure

- `db_connector.py` creates SQLAlchemy connection engines for PostgreSQL and BigQuery using environment configuration.
- `elt_pipeline.py` extracts AdventureWorks tables from PostgreSQL and loads them into BigQuery.
- `adventureworks_analytics/` contains the dbt project, with staging models, reporting marts, macros, SQL tests, and documentation.
- Python dependencies are declared in root `pyproject.toml` and resolved in `uv.lock`.
- Generated dbt artifacts, including `manifest.json` and `run_results.json`, live in `adventureworks_analytics/target/`.

Current source structure (large directories and generated artifacts are collapsed):

```text
Postgres-AdventureWorksDW/
├── .github/workflows/          # Dependency/security audit and user-opened PR links
├── .pre-commit-config.yaml     # Shared pinned local checks
├── .secrets.baseline           # Reviewed secret-scanner false positives
├── AGENTS.md
├── SECURITY_AUDIT.md           # Keep status aligned with docs/SECURITY_AUDIT.md
├── Dockerfile                 # Node auth build → non-root Python/Gunicorn runtime
├── pyproject.toml / uv.lock
├── package.json / package-lock.json
├── db_connector.py            # PostgreSQL and BigQuery SQLAlchemy helpers
├── elt_pipeline.py            # Guarded PostgreSQL → BigQuery WRITE_TRUNCATE ingestion
├── adventureworks_analytics/
│   ├── dbt_project.yml / packages.yml / package-lock.yml
│   ├── models/staging/         # Source normalization
│   ├── models/intermediate/    # int_product_sales
│   ├── models/marts/           # Dimensions, fct_sales, revenue/product/growth/demographic marts
│   ├── macros/ / tests/ / docs/
│   └── target/                # Generated artifacts; not application telemetry
├── my-dash-app/
│   ├── app.py                 # Flask server, auth/cache initialization, Dash shell
│   ├── auth.py / governance.py / rate_limiter.py
│   ├── revenue_kpis.py / wholesale_kpis.py / growth_kpis.py / customer_kpis.py
│   ├── sales_filters.py / customer_map.py
│   ├── analytics.py / data.py / components.py / theme.py
│   ├── pages/                 # Overview, four reports, monitoring, tables, workspace/admin, settings
│   ├── templates/             # Flask landing and authentication pages
│   ├── assets/                # Modular CSS/JS/icons and generated auth.js
│   └── map_data/              # Bundled geographic boundaries and provenance
├── auth_frontend/             # Supabase session, registration, recovery, CSRF and Node tests
├── scripts/                   # Auth build, hook runner, bootstrap and explicit DB test tools
├── supabase/migrations/       # Governance, email-first registration, verified approvals,
│                             # access requests and password lockout
├── supabase/tests/ / supabase/templates/
├── tests/                     # Offline Python regression suite; external services mocked
├── design-system/adventureworks-analytics/
│   ├── MASTER.md
│   └── pages/                 # Auth, landing and workspace-admin overrides
└── docs/                      # Auth, security, caching, bootstrap and ELT operating guides
```

Ignored local state includes `.env`, `gcp-key.json`, `.venv/`, `node_modules/`, caches, logs, and generated dbt outputs. These are not portable source dependencies.

### Current routes and data boundaries

- `/` is the public Flask landing page for visitors without an access cookie; authorized root navigation redirects to `/dashboard`. Authentication, recovery, callback, and access-pending screens are served outside Dash.
- `/dashboard` shows synthetic activity and pipeline summaries. `/monitoring` currently uses sample runs and does not provide live dbt artifact monitoring. `/tables` uses bounded, read-only BigQuery previews of `dim_product`, `dim_customer`, and `fct_sales`; queries return at most 500 displayed rows with a 100 MiB billing cap. Search, sorting, and pagination apply to the loaded preview, not the full warehouse.
- `/dashboard/executive`, `/dashboard/wholesale`, `/dashboard/growth`, and `/dashboard/customers` use warehouse loaders for report analytics. Preserve the calendar year, quarter, channel, category, and dependent subcategory filter contract in `sales_filters.py`.
- Revenue, wholesale, growth, and customer loaders use parameterized read-only BigQuery queries and validated table identifiers. Analytics default to `gold_adventureworks`; wholesale fulfillment also uses `BQ_STAGING_DATASET` (default `silver_adventureworks`). Preserve query billing limits and explicit mart/fact fallbacks.
- `/workspace/admin/members` provides permission-scoped workspace/email/role/access filters, ten memberships per page, and a canonical member details/access modal. `/workspace/admin` uses an independent five-event activity pager. Both read paths require migration `202610150001_admin_directory_activity.sql`, applied to hosted project `lcnsbwohtrxrtissvbzl` on 2026-10-15. Authenticated database reads and anonymous execute denial were verified; this does not establish deployment of the application code.
- `/workspace/admin/create` is the platform-admin-only workspace creation page, opened from Workspace Admin. It validates workspace details and an existing verified owner, then switches to the created workspace through the existing governance RPC.
- `/workspace` loads the selected workspace summary from Supabase; freshness, saved views, quality, and glossary sections still include labeled fixtures. It never runs ingestion or dbt. `/workspace/admin` performs role-authorized governance operations through RPCs.
- `/settings` stores browser display preferences. No credentials or warehouse datasets belong in browser stores.

- Keep credentials and `.env` values out of documentation and version control.
- `elt_pipeline.py` uses `WRITE_TRUNCATE` when loading BigQuery tables; running it replaces destination table data and requires the production confirmation described below.

## 4. General Architecture

- Never use global variables to store user-specific state. Keep mutable client state in `dcc.Store` or URL parameters.
- Use descriptive, globally unique component IDs, such as `"sales-filter-dropdown"`.
- Load data inside callbacks, not at import time. Avoid module-level data reads or database queries; startup-loaded data will not refresh until the process restarts.
- Use a layout function such as `def serve_layout(): ...` when the layout must be rebuilt on each page load.
- Filter, aggregate, and paginate data in Python or SQL before sending it to graphs or `AgGrid`. Send only the rows or points needed for the current view.
- Production Python dependencies and development security tools currently use exact pins in root `pyproject.toml`; preserve those pins and update `uv.lock` when dependencies change.
- Use explicit BigQuery column names, logical filters, and date/time boundaries where applicable. Include a `LIMIT` during structural testing to control scan costs.

## 5. Callbacks, Data, and Performance

- Do not pass massive datasets through `dcc.Store`. Use it only for lightweight state such as IDs, UI toggles, or query filters, with a maximum of 5 MB.
- For large datasets, expensive queries, heavy computations, or API requests, use Flask-Caching and `@cache.memoize()`. Include relevant query parameters in cache keys.
- Ensure every callback `Input`, `Output`, and `State` ID exists in the layout when the callback fires. For dynamic or multi-page layouts, set `suppress_callback_exceptions=True`.
- Use `prevent_initial_call=True` for callbacks that should not run on page load, such as button-triggered actions.
- Return `dash.no_update` when an output should remain unchanged. Use `raise PreventUpdate` when the entire callback should be skipped.
- Keep callbacks focused: prefer one callback per user interaction and split large callbacks into smaller, composable ones.
- Wrap potentially slow components in `dcc.Loading` to show a loading indicator.
- Use background callbacks for work that takes more than a few seconds, with `background=True` and a configured manager such as `manager=background_callback_manager`.
- Return output types appropriate to the component: strings or component lists for `children`, dictionaries for figures, and lists of dictionaries for `AgGrid` `rowData` and `columnDefs`.
- Avoid blocking `time.sleep` loops in callbacks. Use `dcc.Interval` for asynchronous polling or an external task queue for long-running work.

## 6. Layout and Styling

- Prefer Dash Bootstrap Components (`import dash_bootstrap_components as dbc`) for styled UI elements such as cards, badges, buttons, menus, alerts, and modals. Use their built-in properties before creating custom HTML equivalents.
- Keep Bootstrap styling aligned with `design-system/adventureworks-analytics/MASTER.md` and relevant page overrides. Reuse the app's stylesheet setup; when Bootstrap classes are needed, ensure a Bootstrap 5-compatible stylesheet is loaded once and check for conflicts with existing dashboard styles.
- Put core layout styles, grids, and structural overrides in CSS files under `assets/`.
- Use a shared `theme.py` or `theme.js` for color, spacing, and font constants.
- Use inline Python style dictionaries only for dynamic, runtime-computed styling. Avoid static inline style blocks.
- Format Python with `black` and CSS with Prettier.

## 7. Charts and Components

- Prefer `plotly.express`; use `plotly.graph_objects` when fine-grained control is needed.
- Use Dash Bootstrap Components as the preferred styled component library. Continue using Dash Core Components for graphs, stores, routing, and controls where appropriate, Dash HTML Components for semantic structure, and Dash AgGrid for tables. Avoid introducing another UI component library when the existing stack supports the requirement.
- Do not use `dash_table.DataTable`; use `dash.AgGrid`.
- When creating `dag.AgGrid`, set these properties:

```python
dashGridOptions={
    "theme": "themeBalham",
    "animateRows": True,
    "pagination": True,
    "paginationPageSize": 10,
}
columnSize="responsiveSizeToFit"
defaultColDef={"filter": True, "sortable": True}
```

## 8. Observability and New Pages

- Generated dbt artifacts belong in `adventureworks_analytics/target/`. Live artifact telemetry is not currently wired into the sample monitoring page. If added, cache parsed artifacts server-side and send only lightweight summaries to the browser; never reread full manifests on each layout update or polling callback.
- Page layout functions must return quickly with placeholders or empty grids. Do not run database queries or intensive data loaders inside them.
- Fetch data in callbacks triggered by page or tab selection.
- For multi-tab pages, fetch data only for the active tab and return `dash.no_update` for unselected tab outputs.
- Handle `None` and empty DataFrames without column lookup failures or `IndexError`.

## 9. Avoid Hallucinations and Unsafe Patterns

- Use `app.run`; never use `app.run_server`.
- Do not use `app.validation_layout`. For dynamic layouts, use `suppress_callback_exceptions=True` during app initialization.
- Import callback primitives using modern Dash syntax, for example: `from dash import Input, Output, State, callback, clientside_callback, no_update, ALL, MATCH`.
- Never assign to callback `Input` values or mutate callback arguments in place.
- Never put secrets, API keys, or credentials in layout code or `dcc.Store`. Use environment variables and server-side logic.
- Never run destructive commands against production resources without explicit, multi-turn user confirmation.
- For specialized UI additions, check `.agents/skills/` for a relevant task capsule before implementing.
- For interface design, implementation, review, or fixes, read and apply [ui-ux-pro-max](/Users/roelsomido/.codex/skills/ui-ux-pro-max/SKILL.md). Use it for layout, components, accessibility, responsive behavior, typography, colors, charts, and interactions; skip purely non-visual backend work. Read the existing `design-system/adventureworks-analytics/MASTER.md` and relevant page overrides before making visual decisions, and keep implementation aligned with this project's Dash stack.
- When adding or adapting the five sales filters (calendar year, quarter, sales channel, product category, and dependent product subcategory) in Dash reports, read and apply [dash-sales-filters](/Users/roelsomido/.codex/skills/dash-sales-filters/SKILL.md). This globally installed skill covers shared filter behavior, query consistency, browser state, and styling; adapt its field mappings to the target report.

## 10. Production Safety

- The workspace is connected to the production Google Cloud environment `quantum-echo-data-eng-prod`.
- Never run destructive commands such as `bq rm`, `dbt clean`, or commands that drop production datasets without explicit, multi-turn user confirmation.

## 11. Authentication & Access Control

- Keep authentication in the existing Dash/Flask application; do not introduce Next.js routing or SSR middleware. See [Supabase authentication setup](docs/supabase-auth.md).
- Register `install_auth(server)` from `my-dash-app/auth.py` before constructing Dash so authorization runs before Dash request hooks, data callbacks, and exports.
- Serve `/login`, `/signup`, and `/auth/callback` as Flask-rendered pages outside the dashboard layout. Product Overview lives at `/dashboard`; authenticated `/` requests redirect there. Keep navigation and route-dependent callbacks consistent.
- Email/password signup requires email confirmation. Google and GitHub OAuth use PKCE and require separately enabled/configured providers in Supabase. Never assume a rendered provider button means the provider is enabled.
- New accounts register with email/password first, verify email, receive workspace approval, then sign in. Keep social providers off `/signup`; Google/GitHub sign-in may link only to existing matching verified-email accounts. Preserve the `auth.users` email-first registration trigger, do not infer registration from user-editable metadata, and never establish application cookies for unapproved accounts. Email confirmation completes registration without automatic dashboard login.
- Verify access tokens against Supabase Auth on every protected request, then require a confirmed email and current database-managed workspace access. Verified registrations create workspace-scoped access requests. Administrator approval creates membership transactionally; session synchronization only checks current membership. Signup alone grants no access. Never authorize from client state, editable metadata, or unverified JWT claims.
- Keep the public route/asset allowlist explicit. `/auth/config` exposes only the public project URL and anon key; `/auth/session` POST validates the token and sets the access cookie, while DELETE clears it. Authentication endpoints must remain usable before a session exists.
- Require exact `Origin` matching and the cookie-bound `X-CSRF-Token` for browser mutations, including all Dash callback POSTs. GET `/auth/csrf` requires `X-CSRF-Request: 1`; keep issuance separate from session synchronization quotas. Preserve the frontend same-origin mutation allowlist and never replay rejected writes. See [CSRF protection](docs/csrf-protection.md). Cookies must be HttpOnly and SameSite=Lax, with Secure enabled except for explicitly configured HTTP localhost development. Preserve `private, no-store` response headers.
- Keep refresh tokens managed by Supabase JS. Never put access/refresh tokens or provider secrets in `dcc.Store`, logs, templates, or browser configuration.
- Wait for session synchronization before releasing Dash data requests or revealing the dashboard. Preserve token refresh, sign-out across tabs, callback error recovery, and visible startup failure states. Do not automatically replay rejected mutations.
- Return 401 for invalid sessions, 403 for denied access, and 503 for configuration/service failures; fail closed before data loaders run. Redirect unauthorized page navigation to `/login`.
- Read `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` (or legacy `NEXT_PUBLIC_SUPABASE_ANON_KEY`), `AUTH_APP_ORIGIN`, `FLASK_SECRET_KEY`, and `AUTH_OAUTH_PROVIDERS` from root `.env` locally or the deployment environment. Runtime environment values take precedence. Use only the public anon or publishable key in browser configuration; never a service-role key.
- Keep browser and server pointed at the same Supabase project through `/auth/config` at runtime. Do not bake project credentials into portable Docker/CI builds.
- Store only the selected workspace ID in the signed Flask session and revalidate current access on every protected request. Switching workspaces reloads the app shell. All workspaces share the AdventureWorks analytics dataset.
- Govern workspaces through authenticated transactional RPCs with RLS and audit events. Owners manage their workspace; Admins manage Viewers only; Platform Admins provision workspaces. Preserve the last active Owner under a workspace row lock. Bootstrap privileges are CLI-only and never exposed through the app.
- Workspace request decisions and manual email approval require an existing Supabase user with `email_confirmed_at` set, checked server-side by the governance RPC after the actor's role is authorized. Never approve an unknown or unverified email or trust browser-provided verification status.
- Distinguish Google Cloud's authorized redirect URI (`https://<project-ref>.supabase.co/auth/v1/callback`) from Supabase's allowed app redirect URLs (`<app-origin>/auth/callback`). Do not substitute one for the other.
- Edit `auth_frontend/` sources, then run `npm ci` and `npm run build:auth`. Never fix authentication by editing only the generated bundle or disabling the server guard. Exclude the bundle from Dash auto-injection and load it exactly once through the index template.
- Commit the backend, templates, CSS, frontend sources, generated tracked bundle, package manifests, build script, and Docker integration together. Docker builds the bundle in a Node stage and runs only Python/Gunicorn in the final image.
- After auth changes, run `uv run --locked python scripts/pre_commit_checks.py python-tests` and `npm run test:auth`. The wrapper explicitly selects testing rate limits and clears Redis/proxy settings so local `.env` cannot cause production Redis access. Verify unauthenticated page/data access, approval and confirmation checks, expiry/refresh, logout, OAuth errors, and loading states without querying production BigQuery or creating real accounts.

## 12. Local Setup, Verification & CI

See the [personal skills catalog](docs/skills-catalog.md) for available workflows, project-specific examples, and maintenance guidance.

From the repository root:

```sh
uv sync --locked --python 3.12
npm ci
npm run build:auth
uv run --locked pre-commit install
```

Configure private local values using `.env.example` and [Supabase setup](docs/supabase-auth.md). For local memory rate limits, explicitly select `RATE_LIMIT_ENVIRONMENT=development`; production mode is the default and requires Redis. Start the app with `uv run --locked python my-dash-app/app.py` and use the configured `AUTH_APP_ORIGIN`.

Use targeted checks for the files being changed. Relevant commands:

```sh
# Offline Python tests with safe rate-limit overrides and mocked services
uv run --locked python scripts/pre_commit_checks.py python-tests
npm run test:auth

# Reuse the same Bandit settings locally and in CI
uv run --locked pre-commit run bandit --all-files --show-diff-on-failure

# Full repository checks, including network access for dependency advisories
uv run --locked pre-commit run --all-files
```

- `.pre-commit-config.yaml` is the source of hook settings. Commits run staged-file lint, formatting, types, security/secrets, syntax, and hygiene checks, plus the full offline Python and auth frontend suites. See [pre-commit guide](docs/pre-commit.md).
- Bandit is pinned to `1.9.4` and runs with `-ll -ii` (medium/high severity and confidence), excluding `tests/` and `scripts/test_governance_db.py` in addition to shared generated-directory exclusions. Reuse the hook rather than copying its flags/exclusions. Keep reviewed `nosec` annotations narrow; see [security check boundaries](docs/security-checks.md).
- The local dependency hook runs only for `pyproject.toml`/`uv.lock` changes and audits locked runtime **and dev** dependencies. CI's existing `audit` job exports `--no-dev` and runs strict pip-audit against locked **production** dependencies; do not add a duplicate dependency audit when extending CI.
- `.github/workflows/dependency-audit.yml` runs on pull requests and pushes to `integration`/`main`, and Mondays at 09:00 UTC (17:00 Manila), with read-only repository permissions. It is security scanning, not an application deployment or the full pre-commit test suite.
- **Security CI as of 2026-10-15:** the current branch includes `main` commit `8609251`, with an independent pinned Bandit job alongside pip-audit and matching audit status in both reports. Reuse the existing hook configuration when maintaining the workflow.
- `.github/workflows/auto-pr.yml` publishes a compare link into `main` in the Actions run summary on branch pushes other than `main`/`master`. Open the link while signed in and submit the PR as your account; do not recreate bot-authored PRs with `GITHUB_TOKEN`, whose PR workflows require approval and can expire. The link workflow has no token permissions. Existing fork approval policies and the independent audit checks remain in place. See [PR workflow guidance](docs/pull-request-workflow.md). Use pull requests for changes to protected branches; do not rely on rule bypass privileges.
- Docker builds auth assets in Node 22, installs locked production Python dependencies, then runs Gunicorn as non-root `appuser` on port 8050 with two workers. Runtime secrets are supplied separately; a successful local scan does not establish a successful deployment.

## 13. Security State & Operational Boundaries

- SQL identifier validation, exact dependency pins, ELT production guards, authentication rate limits, cookie-bound CSRF, cache coverage regression tests, and bootstrap TLS hardening are implemented in repository code. Keep both [root audit](SECURITY_AUDIT.md) and [docs audit](docs/SECURITY_AUDIT.md) aligned when recording remediation status. Historical assessment allegations are not all current defects; read their implementation evidence.
- Warehouse KPI results use a shared FileSystemCache: typical result TTL is 60 seconds and the filter catalog TTL is 300 seconds. All 21 inventoried memoized loaders have explicit query inputs; see [cache coverage](docs/cache-coverage.md). Workspaces share the same analytics dataset, so current caches may be shared. Any future workspace/user-specific query scope or server-side pagination must enter loader arguments, cache keys, and regression tests.
- Production auth limiting needs shared `RATE_LIMIT_REDIS_URL`; missing or failed storage fails closed. Trust only explicitly configured proxy CIDRs, never blanket forwarded headers. Deployment Redis/proxy validation remains an operational task; see [rate limits](docs/auth-rate-limits.md).
- Keep `SUPABASE_DB_URL` out of the web service, frontend, container build, logs, and tracked files. Bootstrap is CLI-only and enforces a TCP host, certificate/hostname verification (`verify-full`), and negotiated TLS before SQL. See [bootstrap credential runbook](docs/bootstrap-credentials.md). Production credential rotation remains pending separate operator authorization and evidence.
- ELT `--dry-run` performs preflight without clients, source reads, or writes. Production execution requires both `--confirm-production` and an exact `--destination project.dataset`, in addition to multi-turn human authorization. Never use real ELT as a test; see [ELT safety](docs/elt-safety.md).
- Do not run `scripts/test_governance_db.py`, bootstrap, migrations, live account creation, warehouse queries, or production credential operations as part of the offline test suite. Repository tests and scans do not prove live Supabase, warehouse, browser, or deployment behavior.
