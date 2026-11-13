# Vercel Fluid Active CPU — diagnosis and optimization (2026-11-13)

## Why

Vercel flagged `datanerdbytes-4121` (Hobby) at **103% of the included Fluid Active CPU
(4h 42m of 4h)** with the account scheduled to pause on **November 14, 2026** unless
upgraded. This report records where the CPU went and what was changed in
`my-dash-app` to cut future consumption.

## Where the CPU went (last 30 days, Vercel usage dashboard)

| Consumer                                                     | Active CPU | Share |
| ------------------------------------------------------------ | ---------- | ----- |
| adventureworks-analytics (current deploy)                    | 1h 30m     | 31.8% |
| adventureworks-analytics-1794038783087-8aRX (deleted deploy) | 1h 33m     | 33.1% |
| online-portfolio-api                                         | 41m 48s    | 14.8% |
| dbt-bigquery-warehouse                                       | 22m 19s    | 7.9%  |
| online-portfolio                                             | 18m 35s    | 6.6%  |
| ph-news-workbench                                            | 11m 47s    | 4.2%  |

Team-wide: 70,272 function invocations, 84.4 GB-Hrs Fluid provisioned memory
(~10.5 wall-hours of container uptime — consistent with frequent scale-to-zero
cold starts), Build CPU Minutes 11h 18m (separate budget, worth watching).

The deleted adventureworks-analytics deployment burned 1h 33m before being
replaced; the current deployment is running ~50m CPU/day over the last week.

## Root causes found in `my-dash-app`

1. **Every container request bills CPU — including static assets.** Dash/Flask
   served `/assets/*` and `/_dash-component-suite*` uncached, so ~68K CDN
   requests ≈ 70K function invocations. Each cold start re-imports
   dash/plotly/pandas (~1.4s measured for the analytics import alone).
2. **`sales_fixture()` rebuilt on every callback.** A ~4,320-row DataFrame was
   regenerated row-by-row inside `build_report()` for every report page load
   and filter change (~45ms CPU per call, before groupbys and figure JSON).
3. **Warehouse cache expired after 60s.** All ~20 `warehouse_memoize` call
   sites used `timeout=60` (one 300) against a committed, immutable
   `analytics.duckdb` — queries reran every minute regardless of traffic.

## Changes made (uncommitted)

- `my-dash-app/analytics.py` — `@lru_cache(maxsize=1)` on `sales_fixture()`;
  `build_report()` now works on `.copy()` (verified: 45ms → ~0.001ms per call).
- `my-dash-app/warehouse_cache.py` — new `DEFAULT_TIMEOUT_SECONDS` from
  `KPI_CACHE_TIMEOUT_SECONDS` env var, default **3600** (was hard-coded 60).
- `revenue_kpis.py`, `customer_kpis.py`, `wholesale_kpis.py`, `growth_kpis.py`,
  `warehouse_tables.py` — dropped explicit `timeout=60` / `timeout=300`
  arguments so loaders use the new default.
- `my-dash-app/app.py` — `after_request` hook adds
  `Cache-Control: public, max-age=86400, s-maxage=86400` to `/assets/*` and
  `/_dash-component-suite*` (Vercel's edge CDN now serves repeat asset requests
  without waking the container; production caches purge on each deploy), and
  `/theme.css` gets `public, max-age=300, s-maxage=86400`.
- `pyproject.toml` — warehouse pipeline deps (dbt stack, BigQuery/Postgres
  clients) moved into a `warehouse` dependency group; `dev` includes the group
  so local `uv sync` and `uv run dbt` are unchanged.
- `Dockerfile` — image now builds with `uv sync --frozen --no-dev --no-group
warehouse`.

Verified with `py_compile` and a Flask test client: `/theme.css`,
`/_dash-component-suite.js`, and `/assets/*` all return the new headers;
`/dashboard` HTML stays uncached; `build_report("executive", 2026, "All regions")`
returns the expected 7-tuple.

## Expected impact

Asset CDN caching removes roughly 60–70% of container invocations (and their
cold-start imports); the 1-hour warehouse cache cuts DuckDB reruns 60x; fixture
memoization trims per-callback CPU. Together these should keep a full cycle
comfortably inside the 4-hour Hobby allowance at current traffic — no guarantee,
monitor the Usage page after deploy.

## Functions Storage — second email, same day (10 GB / 100%)

A separate allowance from Active CPU. **Functions Storage** counts every retained
deployment's Function bundle, measured in **GB-months**: Vercel records each
project's maximum stored size per billing day and sums those daily amounts over
the cycle. Hobby includes 10 GB-months; at 100% older deployments are
automatically deleted (current production stays live — no outage, only
rollback/preview history shrinks).

Measured bundle sizes (`vercel inspect`, 2026-11-13):

| Project                  | Per-deployment Function bundle        |
| ------------------------ | ------------------------------------- |
| adventureworks-analytics | **550.49 MB** (container image, iad1) |
| online-portfolio-api     | 33.79 MB (sin1)                       |
| ph-news-workbench        | ~1.8 MB per lambda                    |

Why the total is far bigger than the app code: the dashboard container ships the
full `uv sync --frozen --no-dev` environment — including **dbt-core, dbt-bigquery,
dbt, google-cloud-bigquery(+storage), pandas-gbq, sqlalchemy(+bigquery),
psycopg2-binary** — none of which the served app imports (grep-verified; they
belong to the offline warehouse pipeline). Hobby retention additionally keeps the
**last 3 deployments and last 3 Ready production deployments** per project for a
default 30 days, so ~3 × 550 MB ≈ 1.65 GB stays stored for the dashboard project
every day, plus four dashboard deploys on Nov 13 alone. At ~2 GB/day across the
team, the 10 GB-month allowance refills roughly weekly.

### What's actually inside the 550 MB (installed-size measurement)

The app's data artifact (`my-dash-app/data/analytics.duckdb`) is **9.8 MB** — the
dbt models are text SQL and aren't needed at runtime. The bulk is the Python
environment:

| Chunk                        | Installed size | Packages                                                                                                                                         | Needed to serve?                           |
| ---------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------ |
| dbt toolchain                | ~319 MB        | `dbt` (dbt-core, adapters, metricflow) + networkx + sqlglot + rich + pydantic                                                                    | No — offline pipeline only                 |
| Google/BigQuery client stack | ~160 MB        | `google/` (bigquery, grpc, auth, protobuf) + `grpc/` + vertexai + cryptography                                                                   | No — warehouse replaced by DuckDB artifact |
| Database drivers             | ~25 MB         | sqlalchemy + sqlalchemy-bigquery, psycopg2                                                                                                       | No — app reads the local DuckDB file       |
| Serving stack                | ~390 MB        | pyarrow 124 (pandas 3.x hard dependency), plotly 51, pandas 49, duckdb 49, dash 36, babel 33, numpy 25, dash-ag-grid 21, flask/gunicorn/misc ~10 | Yes                                        |
| Base image + app             | ~130 MB        | python:3.12-slim, uv, my-dash-app source + 9.8 MB artifact                                                                                       | Yes                                        |

(Production image syncs `--no-dev`, so dev tools like mypy/mypyc/ruff are not
shipped; the ~550 MB Vercel reports is the compressed no-dev image.)

So **~500 MB of the ~1 GB no-dev environment is pipeline tooling the served app
never imports**. Trimming it plus optional pandas 2.x (drops the 124 MB pyarrow
hard-dependency) puts the bundle in the ~180–250 MB range — roughly half the
Functions Storage burn.

### Recommended fixes (no Pro upgrade needed)

1. **Split warehouse deps out of the runtime image** (biggest lever): move
   dbt/BigQuery/SQLAlchemy/psycopg2 into a uv dependency group and build the
   container with `uv sync --frozen --no-dev --no-group warehouse`. Bundle drops
   550 MB → ~200 MB (pyarrow must stay: pandas 3.x hard-depends on it).
   Caveat: local dbt work then needs `uv sync --group warehouse`.
2. **Shorten retention** for adventureworks-analytics (Project Settings → Build
   and Deployment → Deployment Retention Policy), e.g. Pre-Production 1 day,
   Production 7 days — fewer GB-days retained.
3. **Deploy once per tested change** — every deploy retains another 550 MB bundle.

### Split applied and measured (2026-11-13)

Rebuilt the exact container dependency set from `uv.lock` before/after:

| Environment                                               | Installed size | Requirements |
| --------------------------------------------------------- | -------------- | ------------ |
| Old container set (`--no-dev`, warehouse as project deps) | 914 MB         | 446 packages |
| New container set (`--no-dev --no-group warehouse`)       | **343 MB**     | 86 packages  |

−62% installed environment size (−571 MB); projected compressed Function bundle
550 MB → **~250 MB** per deployment. Smoke test with the slim environment:
`validate_analytics_artifact()` passes, `/dashboard` 200, `/theme.css` 200,
`/` 302, and zero dbt/BigQuery/SQLAlchemy/psycopg2 packages installed. Local
dev environments still receive the warehouse group through `dev → include-group`.

## Not done (needs a decision)

- **Deploy / commit** — left uncommitted for manual testing. Deploy with
  `vercel --prod` from the repo root.
- **Upgrade to Pro ($20/mo)** — the only action that guarantees the team is not
  paused on Nov 14; usage already exceeds the included 4h, and code fixes cannot
  rewind the meter. Decide in the Vercel dashboard (Usage → Upgrade to Pro).
- **online-portfolio-api (15% of CPU)** — FastAPI serverless function; cold-start
  imports likely dominate. Worth a follow-up pass.
