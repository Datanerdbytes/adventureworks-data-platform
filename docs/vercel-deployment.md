# Vercel deployment

The dashboard runs as one Vercel container service. `vercel.json` forces the
`container` framework preset, selects the repository `Dockerfile`, and routes every
request to the `dashboard` service. The single-stage build installs locked
production Python dependencies and runs Gunicorn as non-root `appuser`.

The application is public: no authentication, no Supabase configuration, and no
Redis are required to deploy or serve it. Historical authentication documentation
under `docs/` describes the retired system, not the current runtime.

## Warehouse data

The runtime no longer queries BigQuery and needs no Google credentials. Reports and
table previews read `my-dash-app/data/analytics.duckdb`, the committed export of the
`gold_adventureworks` tables plus the staging fact used by the wholesale
fulfillment loader. `Dockerfile` copies the whole `my-dash-app` directory, so the
artifact ships in the image; `.vercelignore` must not exclude `my-dash-app/data`.

`scripts/vercel_start.py` opens the artifact read-only and checks that
`gold_adventureworks` contains tables before replacing itself with Gunicorn. A
missing, empty, or unreadable artifact fails the container startup with build
instructions instead of serving reports that fail on first query.

Keep the artifact in sync with the dbt models before deploying:

```sh
uv run --locked python scripts/verify_shipped_gold.py
```

Rebuild and export it only from the offline DuckDB build:

```sh
uv run --locked python -B scripts/load_bronze_duckdb.py
# run dbt build against adventureworks_analytics/build/analytics.duckdb
uv run --locked python scripts/export_gold_duckdb.py
```

`GOLD_DATABASE_PATH` overrides the artifact location for unusual mounts. It defaults
to the bundled file; leave it unset for the standard image.

## Runtime configuration

The container needs no project environment variables. `PORT` is baked into the
image (default `8050`); Vercel's container runtime routes traffic to the port the
`PORT` environment variable selects, so leave the default unless the platform
injects a different value.

Google Cloud project, dataset, and service-account variables are not part of the
runtime contract. The legacy ingestion and BigQuery tooling in `elt_pipeline.py`
remains an explicit operator path; the container does not read those settings.

`.vercelignore` excludes local secrets, environments, tests, and unrelated pipeline
artifacts from uploads. `.vercel/` and `.env` stay out of Git. Never bake secrets
into the image.

## Deploy and verify

Deployments run through GitHub Actions (`.github/workflows/deploy-vercel.yml`), so
no local Vercel CLI sign-in is required. The workflow deploys **previews** on
pull requests and pushes to `main`; production traffic moves only when the
workflow is run manually with the target set to `production`.

One-time setup:

1. Create a Vercel access token (Account Settings → Tokens, scope it to the
   `adventureworks-analytics` project's team) and store it as the repository
   secret `VERCEL_TOKEN` with `gh secret set VERCEL_TOKEN`.
2. Store the org and project identifiers as `VERCEL_ORG_ID` and
   `VERCEL_PROJECT_ID`. The current values come from `.vercel/project.json`
   (`team_aWWXAsZiAMPGuRFGhIqQyyFA`, `prj_nff006qKUhdUdIHrNXKFwjfvE62w`); if the
   project is re-imported, replace both secrets with the new identifiers.

Preview verification before a production release:

- `/` redirects to `/dashboard` and the dashboard shell renders without a
  sign-in wall.
- Revenue, wholesale, growth, customer, and table preview pages render from the
  shipped artifact and keep the five sales filters working.

Container functions scale independently, so each instance has its own temporary
FilesystemCache for report results. Deployment does not run ingestion, dbt, or SQL
migrations.

## Deployment history

A production deployment on 2026-10-20 used the previous BigQuery-backed runtime and
runtime-materialized Google credentials. That shape is not current: the startup
helper now validates the DuckDB artifact and no Google secret is configured.

On 2026-11-12 the runtime became fully public (authentication removed) and the
deploy configuration was hardened: `vercel.json` forces the container framework
preset, the CLI pin was bumped for the container/services beta, and the workflow
fails when no deployment URL is produced. Promote to production with a manual
workflow run (`target=production`) after the preview checks above pass.
