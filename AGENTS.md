# Current access model — public app (2026-11-12)

The owner removed authentication on 2026-11-12: the deployed dashboard is public
and no sign-in is required. Supabase auth, workspace governance, account
management, CSRF, and Redis rate limiting were deleted from the runtime; the
`supabase/` migrations and governance operator scripts remain only as historical,
unused tooling. `/` redirects to `/dashboard`. No Supabase, Redis, or secret
environment variables are required to run or deploy the app. Keep the warehouse
boundaries below: reports read only the committed DuckDB artifact. Do not
reintroduce authentication or deploy without explicit authorization.

# Agent Context & Rules

Repository state reviewed: **2026-11-12**. This guide describes checked-in behavior; production configuration and deployment must be verified separately.

## 1. Project Overview

- **Project Name:** AdventureWorks Analytics (Data Analytics Dashboard)
- **Core Purpose:** A public, sign-in-free Dash analytics application whose sales reports read a committed DuckDB artifact, plus retained PostgreSQL → BigQuery ingestion and dbt transformation tooling. Dashboard activity and pipeline monitoring currently include synthetic fixtures; do not describe them as live telemetry.
- **Target Audience:** Internal business analysts, data engineers, and stakeholders.

## 2. Tech Stack & Environment

- **Language:** Python 3.12 locally and in Docker; `pyproject.toml` requires Python >=3.12
- **Python Dependencies:** Root `pyproject.toml` and `uv.lock`, managed with uv
- **Core Framework:** Plotly Dash
- **Underlying Engine:** Flask, including Flask-Caching
- **Formatting Tooling:** Node.js 22+ and npm for Prettier formatting checks
- **Data Engine:** DuckDB read-only artifact at `my-dash-app/data/analytics.duckdb`; dbt builds the models offline, while the current monitoring UI uses fixtures
- **Data Libraries:** `duckdb`, `pandas`, `pyarrow`, `json`; BigQuery libraries remain for explicit ingestion tooling
- **Caching Framework:** Flask-Caching with FileSystemCache for warehouse results (each container instance has its own `/tmp` cache)
- **Styling:** Dash component libraries and modular CSS
- **Code Quality:** Pinned Ruff, Black, mypy, Bandit, detect-secrets, pip-audit, and pre-commit; Prettier for CSS, JavaScript, JSON, YAML, and Markdown

## 3. Architecture & File Structure

- `warehouse_client.py` validates and reads the shipped DuckDB artifact with `$name` parameter binding; it is the runtime query seam.
- `db_connector.py` creates SQLAlchemy connection engines for PostgreSQL and BigQuery using environment configuration.
- `elt_pipeline.py` extracts AdventureWorks tables from PostgreSQL and loads them into BigQuery as an explicit operator tool.
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
├── Dockerfile                 # Single-stage Python build → non-root Gunicorn runtime
├── vercel.json / .vercelignore # Container service routing and upload exclusions
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
│   ├── app.py                 # Flask server, cache initialization, Dash shell
│   ├── revenue_kpis.py / wholesale_kpis.py / growth_kpis.py / customer_kpis.py
│   ├── warehouse_client.py     # Read-only DuckDB artifact query seam
│   ├── data/analytics.duckdb   # Committed runtime reporting artifact
│   ├── sales_filters.py / customer_map.py
│   ├── analytics.py / data.py / components.py / theme.py
│   ├── pages/                 # Overview, four reports, monitoring, tables, workspace, settings
│   ├── templates/             # Shared Flask template fragment (theme script)
│   ├── assets/                # Modular CSS/JS/icons
│   └── map_data/              # Bundled geographic boundaries and provenance
├── scripts/                   # Artifact export/verify, hook runner and operator tools
├── supabase/migrations/       # Historical governance migrations (unused by the public app)
├── supabase/tests/ / supabase/templates/
├── tests/                     # Offline Python regression suite; external services mocked
├── design-system/adventureworks-analytics/
│   ├── MASTER.md
│   └── pages/                 # Page-level design overrides (auth/landing historical)
└── docs/                      # Deployment, security, caching and ELT operating guides
```

Ignored local state includes `.env`, `gcp-key.json`, `.venv/`, `node_modules/`, caches, logs, and generated dbt outputs. These are not portable source dependencies.

### Current routes and data boundaries

- `/` redirects to `/dashboard`; the app is public and every page is reachable without signing in.
- `/dashboard` shows synthetic activity and pipeline summaries. `/monitoring` currently uses sample runs and does not provide live dbt artifact monitoring. `/tables` uses bounded, read-only DuckDB previews of `dim_product`, `dim_customer`, and `fct_sales`; queries return at most 500 displayed rows. Search, sorting, and pagination apply to the loaded preview, not the full dataset.
- `/dashboard/executive`, `/dashboard/wholesale`, `/dashboard/growth`, and `/dashboard/customers` use warehouse loaders for report analytics. Preserve the calendar year, quarter, channel, category, and dependent subcategory filter contract in `sales_filters.py`.
- Revenue, wholesale, growth, and customer loaders use parameterized, read-only DuckDB queries through `warehouse_client.query_rows()` and validated table identifiers. The artifact exposes `gold_adventureworks` and `silver_adventureworks` schemas with the former dataset names. Bind only named `$name` parameters the SQL consumes, and preserve explicit mart/fact fallbacks.
- `/workspace` renders the workspace summary and sample sections; freshness, saved views, quality, and glossary sections still include labeled fixtures. It never runs ingestion or dbt.
- `/settings` stores browser display preferences. No credentials or warehouse datasets belong in browser stores.

- Keep credentials and `.env` values out of documentation and version control.
- `elt_pipeline.py` uses `WRITE_TRUNCATE` when loading BigQuery tables; running it replaces destination table data and requires the production confirmation described below. It is not part of the app runtime.

## 4. General Architecture

- Never use global variables to store user-specific state. Keep mutable client state in `dcc.Store` or URL parameters.
- Use descriptive, globally unique component IDs, such as `"sales-filter-dropdown"`.
- Load data inside callbacks, not at import time. Avoid module-level data reads or database queries; startup-loaded data will not refresh until the process restarts.
- Use a layout function such as `def serve_layout(): ...` when the layout must be rebuilt on each page load.
- Filter, aggregate, and paginate data in Python or SQL before sending it to graphs or `AgGrid`. Send only the rows or points needed for the current view.
- Production Python dependencies and development security tools currently use exact pins in root `pyproject.toml`; preserve those pins and update `uv.lock` when dependencies change.
- Use explicit warehouse column names, logical filters, and date/time boundaries where applicable. Bind values through named parameters and bound previews during structural testing.

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

- The legacy ingestion tooling targets the production Google Cloud environment `quantum-echo-data-eng-prod`; the deployed report runtime reads only the committed DuckDB artifact.
- Never run destructive commands such as `bq rm`, `dbt clean`, or commands that drop production datasets without explicit, multi-turn user confirmation.

## 11. Access Model

- The application is public by owner decision (2026-11-12): no authentication, no sign-in, and no user-specific server state. Do not reintroduce auth guards, Supabase dependencies, CSRF requirements, or sign-in pages without an explicit owner request.
- `/` redirects to `/dashboard`; all dashboard pages, reports, monitoring, tables, workspace, and settings views are reachable anonymously.
- Keep secrets out of the browser: no credentials, tokens, or warehouse data in `dcc.Store`, templates, or client configuration.

## 12. Local Setup, Verification & CI

See the [personal skills catalog](docs/skills-catalog.md) for available workflows, project-specific examples, and maintenance guidance.

From the repository root:

```sh
uv sync --locked --python 3.12
npm ci
uv run --locked pre-commit install
```

The app needs no credentials; `.env.example` documents the optional overrides. Start the app with `uv run --locked python my-dash-app/app.py`.

Use targeted checks for the files being changed. Relevant commands:

```sh
# Offline Python tests with mocked services
uv run --locked python scripts/pre_commit_checks.py python-tests

# Reuse the same Bandit settings locally and in CI
uv run --locked pre-commit run bandit --all-files --show-diff-on-failure

# Full repository checks, including network access for dependency advisories
uv run --locked pre-commit run --all-files
```

- `.pre-commit-config.yaml` is the source of hook settings. Commits run staged-file lint, formatting, types, security/secrets, syntax, and hygiene checks, plus the full offline Python suite. See [pre-commit guide](docs/pre-commit.md).
- Bandit is pinned to `1.9.4` and runs with `-ll -ii` (medium/high severity and confidence), excluding `tests/` and `scripts/test_governance_db.py` in addition to shared generated-directory exclusions. Reuse the hook rather than copying its flags/exclusions. Keep reviewed `nosec` annotations narrow; see [security check boundaries](docs/security-checks.md).
- The local dependency hook runs only for `pyproject.toml`/`uv.lock` changes and audits locked runtime **and dev** dependencies. CI's existing `audit` job exports `--no-dev` and runs strict pip-audit against locked **production** dependencies; do not add a duplicate dependency audit when extending CI.
- `.github/workflows/dependency-audit.yml` runs on pull requests and pushes to `integration`/`main`, and Mondays at 09:00 UTC (17:00 Manila), with read-only repository permissions. It is security scanning, not an application deployment or the full pre-commit test suite.
- **Security CI as of 2026-10-15:** the current branch includes `main` commit `8609251`, with an independent pinned Bandit job alongside pip-audit and matching audit status in both reports. Reuse the existing hook configuration when maintaining the workflow.
- `.github/workflows/auto-pr.yml` publishes a compare link into `main` in the Actions run summary on branch pushes other than `main`/`master`. Open the link while signed in and submit the PR as your account; do not recreate bot-authored PRs with `GITHUB_TOKEN`, whose PR workflows require approval and can expire. The link workflow has no token permissions. Existing fork approval policies and the independent audit checks remain in place. See [PR workflow guidance](docs/pull-request-workflow.md). Use pull requests for changes to protected branches; do not rely on rule bypass privileges.
- Docker installs locked production Python dependencies in a single stage, ships `my-dash-app/data/analytics.duckdb`, then runs Gunicorn as non-root `appuser` on port 8050 with two workers. A successful local scan does not establish a successful deployment. See [Vercel deployment](docs/vercel-deployment.md).

## 13. Security State & Operational Boundaries

- SQL identifier validation, exact dependency pins, ELT production guards, cache coverage regression tests, and bootstrap TLS hardening are implemented in repository code. Keep both [root audit](SECURITY_AUDIT.md) and [docs audit](docs/SECURITY_AUDIT.md) aligned when recording remediation status. Historical assessment allegations are not all current defects; read their implementation evidence.
- Warehouse KPI results use a shared FileSystemCache: typical result TTL is 60 seconds and the filter catalog TTL is 300 seconds. All 21 inventoried memoized loaders have explicit query inputs; see [cache coverage](docs/cache-coverage.md). All visitors share the same analytics dataset, so caches may be shared. Any future per-user query scope or server-side pagination must enter loader arguments, cache keys, and regression tests.
- Historical (auth removed 2026-11-12): keep `SUPABASE_DB_URL` out of the web service, frontend, container build, logs, and tracked files. The retained bootstrap/operator scripts enforce a TCP host, certificate/hostname verification (`verify-full`), and negotiated TLS before SQL. See the [bootstrap credential runbook](docs/bootstrap-credentials.md).
- ELT `--dry-run` performs preflight without clients, source reads, or writes. Production execution requires both `--confirm-production` and an exact `--destination project.dataset`, in addition to multi-turn human authorization. Never use real ELT as a test; see [ELT safety](docs/elt-safety.md).
- Do not run the historical governance/account operator scripts (`scripts/test_governance_db.py`, `scripts/bootstrap_workspace.py`), migrations, live account operations, live warehouse queries, or production credential operations as part of the offline test suite. Repository tests and scans do not prove live warehouse, browser, or deployment behavior.
