# Vercel deployment

The dashboard runs as one Vercel container service. `vercel.json` selects the
repository `Dockerfile`, routes every request to the `dashboard` service, and sets
`PORT=8050`. The Docker build produces the authentication bundle, installs locked
production Python dependencies, and runs Gunicorn as non-root `appuser`.

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

Configure these server-side values on the intended Vercel project:

- The Supabase public URL/key and the server-only service-role key.
- A stable `FLASK_SECRET_KEY` and the exact HTTPS `AUTH_APP_ORIGIN` of the deployed
  application. Allow its callback and recovery URLs in Supabase.
- `RATE_LIMIT_ENVIRONMENT=production` and a reachable Redis connection in
  `RATE_LIMIT_REDIS_URL`. Never substitute process-local development limiting.
- `AUTH_OAUTH_PROVIDERS` only for providers that are enabled in Supabase **and**
  whose client credentials still complete a round trip. A provider whose OAuth
  client was deleted fails at the provider, not in this app; remove it from the
  list and see [provider recovery](supabase-auth.md#recovering-a-deleted-oauth-client).
  As of 2026-11-11 this value is empty in the local environment because the Google
  client was deleted; set the deployed value the same way until the client is
  recreated.
- Keep password lockout disabled until its coordinated migration/hook rollout is
  complete; see [account management](account-management.md).

Google Cloud project, dataset, and service-account variables are not part of the
runtime contract. The legacy ingestion and BigQuery tooling in `elt_pipeline.py`
remains an explicit operator path; the container does not read those settings.

`.vercelignore` excludes local secrets, environments, tests, and unrelated pipeline
artifacts from uploads. `.vercel/` and `.env` stay out of Git. Never bake secrets or
service-role keys into the image.

## Deploy and verify

This checkout does not choose a project implicitly. Verify the linked owner/project
with `vercel project inspect --non-interactive`; use `vercel link` only after
selecting the intended account and project.

Deploy a preview with `vercel deploy`, inspect the build with `vercel inspect`, then
verify before a production release:

- The public landing, login, and `/auth/config` routes return expected responses.
- Anonymous Dash layout and callback requests are denied by the Flask guard.
- CSRF issuance and a verified sign-in work with the deployed origin.
- Revenue, wholesale, growth, customer, and table preview pages render from the
  shipped artifact and keep the five sales filters working.

Container functions scale independently, so each instance has its own temporary
FilesystemCache for report results. Redis remains the shared authentication rate
limiter. Deployment does not run ingestion, dbt, or SQL migrations, and it does not
change Supabase provider or redirect settings.

## Deployment history

A production deployment on 2026-10-20 used the previous BigQuery-backed runtime and
runtime-materialized Google credentials. That shape is not current: the startup
helper now validates the DuckDB artifact and no Google secret is configured. This
branch adds the artifact runtime configuration but does not itself deploy it. Run
the preview checks above before treating the hosted application as migrated.
