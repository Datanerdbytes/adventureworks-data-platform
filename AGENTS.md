# Agent Context & Rules

## 1. Project Overview
- **Project Name:** Data Analytics Dashboard
- **Core Purpose:** An interactive multi-page dashboard to visualize live data tables from Google BigQuery and provide an analytics layer pipeline monitoring console.
- **Target Audience:** Internal business analysts, data engineers, and stakeholders.

## 2. Tech Stack & Environment
- **Language:** Python 3.12 locally and in Docker; `pyproject.toml` requires Python >=3.12
- **Python Dependencies:** Root `pyproject.toml` and `uv.lock`, managed with uv
- **Core Framework:** Plotly Dash
- **Underlying Engine:** Flask, including Flask-Caching
- **Authentication:** Supabase Auth with `@supabase/supabase-js`, OAuth PKCE, and Flask server-side authorization
- **Frontend Build:** Node.js 22+, npm, and esbuild for the authentication bundle
- **Data Engine:** Google BigQuery via Application Default Credentials (ADC), plus dbt artifact telemetry
- **Data Libraries:** `google-cloud-bigquery`, `pandas`, `pandas-gbq`, `pyarrow`, `json`
- **Caching Framework:** Flask-Caching with FileSystemCache or Redis
- **Styling:** Dash component libraries and modular CSS
- **Code Formatters:** `black` for Python and Prettier for CSS

## 3. Architecture & File Structure
- `db_connector.py` creates SQLAlchemy connection engines for PostgreSQL and BigQuery using environment configuration.
- `elt_pipeline.py` extracts AdventureWorks tables from PostgreSQL and loads them into BigQuery.
- `adventureworks_analytics/` contains the dbt project, with staging models, reporting marts, macros, SQL tests, and documentation.
- Python dependencies are declared in root `pyproject.toml` and resolved in `uv.lock`.
- Generated dbt artifacts, including `manifest.json` and `run_results.json`, live in `adventureworks_analytics/target/`.

Current project structure (environment, dependency, cache, log, and generated artifact directories are collapsed; Git internals are omitted):

```text
Postgres-AdventureWorksDW/
├── .env  # Local environment configuration
├── .gitignore
├── .venv/  # Local Python environment
├── __pycache__/  # Generated Python bytecode
├── adventureworks_analytics/  # dbt analytics project
│   ├── .gitignore
│   ├── analyses/
│   │   └── .gitkeep
│   ├── dbt_packages/  # Installed dbt dependencies
│   ├── dbt_project.yml
│   ├── docs/
│   │   ├── LINEAGE.md
│   │   └── PROJECT_GUIDE.md
│   ├── logs/  # Generated logs
│   ├── macros/
│   │   ├── ' generate_schema_name.sql'
│   │   └── .gitkeep
│   ├── models/
│   │   ├── marts/
│   │   │   ├── dim_customer.sql
│   │   │   ├── dim_date.sql
│   │   │   ├── dim_product.sql
│   │   │   ├── dim_reseller.sql
│   │   │   ├── dim_sales_territory.sql
│   │   │   ├── fct_sales.sql
│   │   │   └── marts.yml
│   │   ├── overview.md
│   │   └── staging/
│   │       ├── schema.yml
│   │       ├── sources.yml
│   │       ├── stg_customer.sql
│   │       ├── stg_dim_date.sql
│   │       ├── stg_dim_date.yml
│   │       ├── stg_fact_internet_sales.sql
│   │       ├── stg_fact_reseller_sales.sql
│   │       ├── stg_fact_reseller_sales.yml
│   │       └── stg_product.sql
│   ├── package-lock.yml
│   ├── packages.yml
│   ├── README.md
│   ├── seeds/
│   │   └── .gitkeep
│   ├── snapshots/
│   │   └── .gitkeep
│   ├── target/  # Generated dbt artifacts and documentation
│   └── tests/
│       ├── .gitkeep
│       ├── dim_customer_matches_staging_and_geography.sql
│       ├── generic/
│       │   ├── test_date_continuity.sql
│       │   ├── test_finished_product_coverage.sql
│       │   ├── test_mart_date_attributes.sql
│       │   ├── test_no_unwanted_spaces.sql
│       │   ├── test_not_empty.sql
│       │   ├── test_product_version_date_boundaries.sql
│       │   ├── test_required_values_present.sql
│       │   ├── test_reseller_source_alignment.sql
│       │   ├── test_territory_country_group_consistency.sql
│       │   └── test_territory_source_alignment.sql
│       ├── stg_dim_date_calendar_consistency.sql
│       ├── stg_dim_date_no_gaps.sql
│       └── stg_fact_reseller_sales_matches_source.sql
├── AGENTS.md
├── db_connector.py  # PostgreSQL and BigQuery connection helpers
├── elt_pipeline.py  # PostgreSQL → BigQuery ingestion
├── gcp-key.json  # Local Google Cloud credentials
├── logs/  # Generated logs
├── pyproject.toml
└── uv.lock
```

- Keep credentials and `.env` values out of documentation and version control.
- `elt_pipeline.py` uses `WRITE_TRUNCATE` when loading BigQuery tables; running it replaces destination table data and requires the production confirmation described below.

## 4. General Architecture
- Never use global variables to store user-specific state. Keep mutable client state in `dcc.Store` or URL parameters.
- Use descriptive, globally unique component IDs, such as `"sales-filter-dropdown"`.
- Load data inside callbacks, not at import time. Avoid module-level data reads or database queries; startup-loaded data will not refresh until the process restarts.
- Use a layout function such as `def serve_layout(): ...` when the layout must be rebuilt on each page load.
- Filter, aggregate, and paginate data in Python or SQL before sending it to graphs or `AgGrid`. Send only the rows or points needed for the current view.
- Pin minimum or exact versions of Dash, Plotly, and component libraries in root `pyproject.toml` and update `uv.lock` when dependencies change.
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
- Do not read `analytics_layer/target/manifest.json` from dynamic layout updates or loop callbacks. Reuse cached manifest dictionaries through a `dcc.Store` where appropriate.
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
- Verify access tokens against Supabase Auth on every protected request, then require a confirmed email on the case-insensitive, exact-email `AUTH_ALLOWED_EMAILS` allowlist. An empty allowlist denies everyone. Never authorize from client state, editable metadata, or unverified JWT claims.
- Keep the public route/asset allowlist explicit. `/auth/config` exposes only the public project URL and anon key; `/auth/session` POST validates the token and sets the access cookie, while DELETE clears it. Authentication endpoints must remain usable before a session exists.
- Require exact `Origin` matching for mutations. Cookies must be HttpOnly and SameSite=Lax, with Secure enabled except for explicitly configured HTTP localhost development. Preserve `private, no-store` response headers.
- Keep refresh tokens managed by Supabase JS. Never put access/refresh tokens, provider secrets, or the approval allowlist in `dcc.Store`, logs, templates, or browser configuration.
- Wait for session synchronization before releasing Dash data requests or revealing the dashboard. Preserve token refresh, sign-out across tabs, callback error recovery, and visible startup failure states. Do not automatically replay rejected mutations.
- Return 401 for invalid sessions, 403 for denied access, and 503 for configuration/service failures; fail closed before data loaders run. Redirect unauthorized page navigation to `/login`.
- Read `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `AUTH_APP_ORIGIN`, and `AUTH_ALLOWED_EMAILS` from root `.env` locally or the deployment environment. Runtime environment values take precedence. Use only the public anon key in browser configuration; never a service-role key.
- Keep browser and server pointed at the same Supabase project. The default build uses `/auth/config` at runtime; optional build-time public values override it. Leave build-time values unset for portable Docker/CI builds.
- Distinguish Google Cloud's authorized redirect URI (`https://<project-ref>.supabase.co/auth/v1/callback`) from Supabase's allowed app redirect URLs (`<app-origin>/auth/callback`). Do not substitute one for the other.
- Edit `auth_frontend/` sources, then run `npm ci` and `npm run build:auth`. Never fix authentication by editing only the generated bundle or disabling the server guard. Exclude the bundle from Dash auto-injection and load it exactly once through the index template.
- Commit the backend, templates, CSS, frontend sources, generated tracked bundle, package manifests, build script, and Docker integration together. Docker builds the bundle in a Node stage and runs only Python/Gunicorn in the final image.
- After auth changes, run `.venv/bin/python -B -m unittest discover -s tests -v` and `npm run test:auth`. Verify unauthenticated page/data access, approval and confirmation checks, expiry/refresh, logout, OAuth errors, and loading states without querying production BigQuery or creating real accounts.
