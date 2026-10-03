# AdventureWorks Analytics — local demo

A four-page Dash console with a collapsible sidebar, responsive mobile drawer,
Plotly charts, and searchable AG Grid tables. Charts and detail tables use deterministic synthetic examples. Executive KPI
cards read the BigQuery revenue mart and sales fact. Refresh updates the display timestamp,
not the fixture period. No ingestion or dbt jobs are executed. The five Executive KPIs make a read-only BigQuery query; other displays remain synthetic. The public landing
page lives at `/`; the workspace is protected by temporary `dash-auth` HTTP
Basic authentication. Deployment and Supabase integration remain deferred.

## Run

From the repository root, with Python 3.12+ and uv:

```sh
uv sync
uv run python my-dash-app/app.py
```

Open http://localhost:8050/ for the public landing page. Before signing in, set
`DASH_AUTH_USERNAME` and `DASH_AUTH_PASSWORD` in the root `.env` or runtime
environment, then restart the app. Runtime values take precedence. Choose your
own credentials; there are no default accounts and no credentials are committed.

“Sign in” and “Open workspace” open `/dashboard`, which redirects browser
navigation to an in-page `/login` form. This works in embedded previews that do
not support native Basic Auth prompts. Explicit HTTP Basic Auth requests remain
supported. Missing configuration returns 503; invalid credentials
return 401. Every dashboard page, asset, layout endpoint, and callback requires
valid credentials. A caller-supplied public pathname cannot bypass protection.
Only `/`, `/theme.css`, and `/assets/landing.css` are public GET/HEAD endpoints.

Mutation requests require a matching Origin. If `AUTH_APP_ORIGIN` is set, it must
match the exact address used in the browser; otherwise the current request origin
is used. The server binds only to loopback. Use HTTPS before hosting Basic Auth
outside localhost.

Basic Auth is browser-managed: it has no reliable application logout, signup,
password reset, or cross-tab session controls. To switch accounts, use a separate
private browsing session. The account menu intentionally does not pretend to
log the browser out. Username display comes from the authenticated request;
passwords never enter a layout, Store, or session cookie.

## Pages and preferences

- `/dashboard`: activity, metrics, recent runs, and workspace details.
- `/monitoring`: pipeline and sample-window filters, duration chart, refresh, run grid.
- `/tables`: Products, Customers, and Sales; global search and column sorting/filtering.
- `/settings`: browser-local page size (10, 20, or 50) and sidebar collapse toggle.
- `/`: public SaaS landing page; unknown workspace URLs render a protected fallback page.

The bottom-left avatar and chevron open an account disclosure containing settings,
a link back to the website, and the sidebar toggle. Desktop navigation collapses
from 248px to 72px and remembers the choice in this browser. Below 768px, navigation becomes a modal drawer with Escape dismissal,
focus trapping, and focus restoration. Display preferences are local `dcc.Store`
values; they contain no data or credentials.

## Structure and extension

`app.py` creates the shared shell and routes. `auth.py` installs authentication
before Dash request hooks and uses `dash-auth` with a strict request guard.
`templates/landing.html` and `assets/landing.css` render the public landing page. `pages/` owns page layouts and
callbacks; `components.py` holds reusable UI. `data.py` generates small fixtures
inside callbacks. `theme.py` supplies shared CSS tokens and Plotly styles. Assets
contain modular CSS, local SVG icons, and drawer interaction code.

Add future data services behind the callback layer; implement the repository's
Supabase guard before adding live connections. Never add queries to layout
functions or module imports. The current small fixture callbacks need no cache
or background worker.

## Checks

```sh
.venv/bin/python -B -m unittest discover -s tests -v
uv run black --target-version py312 --check my-dash-app tests
npx --yes prettier --check 'my-dash-app/assets/*.css' 'my-dash-app/assets/*.js' my-dash-app/templates/landing.html
```

Test browser navigation/back/forward, refresh, grid search/sort/filter/pagination,
settings across reloads, sidebar persistence, keyboard focus, and drawer Escape
at 375px, 768px, 1024px, and 1440px. Check empty search results and unknown routes.

## Dashboard report pages

Dashboard now has an expandable Reports submenu plus four report cards on its
Overview. Deep links open the submenu and identify the active report. In the
collapsed rail, the Dashboard chevron expands the sidebar to reveal reports.

- `/dashboard/executive`: Executive Revenue & Sales Performance.
- `/dashboard/wholesale`: B2B Wholesale & Reseller Analytics.
- `/dashboard/growth`: Time-Series Growth & Seasonal Dynamics.
- `/dashboard/customers`: Customer Demographics & Regional Footprint.

Each page has sample-year and region filters, four KPIs, two charts, and a
paginated detail grid. Filters persist for the browser session. Tables respect
Settings page size. Reports use an independent deterministic synthetic order
fixture for 2025–2026; no BigQuery queries run. Amounts are USD and illustrative.
Wholesale uses reseller-channel orders; demographics deduplicate Internet-channel
customers. Growth compares both years but uses the selected year for detail and
month-over-month metrics, including the prior December baseline when available.


## Executive warehouse filters and metrics

`/dashboard/executive` uses four page-wide filter groups: calendar year/quarter,
sales channel, product category, and dependent product subcategory. Defaults are
All. Options come from the revenue mart (currently calendar years 2010–2014);
these are calendar periods, not fiscal periods. Choosing Bikes narrows the
subcategory choices to Mountain Bikes, Road Bikes, and Touring Bikes. An invalid
prior subcategory resets to All when its parent category changes.

All five KPI cards, both charts, and the product-detail table use the same
parameterized warehouse selection. No sample values remain on this page. Other
report pages keep their existing synthetic fixtures and filters.

Revenue and profit sum the filtered `revenue_sales_performance` mart. Margin is
combined profit / revenue × 100. Orders count distinct channel/order pairs from
`fct_sales` joined to `dim_date` and `dim_product`, using the same filters and
Unknown-product fallback as the dbt model. AOV divides selected revenue by
purchasing orders; with product filters it represents selected-product spend per
order, not the entire basket. Product-level order counts are never summed.

The query uses ADC, `GBQ_PROJECT_ID`, and optional `BQ_ANALYTICS_DATASET` (default
`gold_adventureworks`). Aggregate queries are read-only, capped at 100 MiB billed,
and cached for 60 seconds per project, dataset, and full filter tuple. Catalog
options are cached for five minutes. No data query runs at import or in layouts.
Empty selections show zero revenue/profit/orders and undefined ratios as em
dashes. Query failures clear the old results and show an error instead of demo
values. Reload to retry. Tests use mocks for warehouse access.


### Embedded preview sign-in

The `/login` form checks the same configured credentials and establishes a signed,
HttpOnly, SameSite=Lax session lasting up to eight hours. POST requires a CSRF
token and an exact Origin match. Credentials never enter the cookie. Changing
configured credentials invalidates existing sessions. Missing configuration and
unauthenticated data/callback requests still fail closed.

Set `FLASK_SECRET_KEY` in the runtime environment for a stable signing key across
restarts/workers. Without it, the local single-process server generates a random
key at startup, so restarting requires signing in again. Secure cookies are
used when `AUTH_APP_ORIGIN` is HTTPS; HTTP is intended only for local development.

### Wholesale fulfillment matrix

The wholesale table uses `stg_fact_reseller_sales` from `BQ_STAGING_DATASET`
(default `silver_adventureworks`), joined to the analytics date, product, and
reseller dimensions. All five warehouse filters apply. Invoice counts are distinct
per reseller; average units divide filtered units by matching invoices. Shipping
lead days use calendar-date differences, averaged within invoice and then across
invoices, ignoring missing shipping dates. Missing lead times display an em dash.
Buyer geography comes from the reseller state/province and country. Per requested
business display mapping, A and M show Monthly, Q Quarterly, and S Semiannually.
Values above 5 days are red and labeled Over target. Results are capped at 1,000
accounts; exceeding the cap prompts narrower filters instead of silently truncating.

### Growth scorecards

The five Growth KPIs use `marts_growth_trends` for monthly revenue history. Since
that mart has no dates or product hierarchy, product-filtered monthly totals are
recomputed from `fct_sales` with date/product dimensions. Daily invoice totals
from the same facts support rolling revenue and velocity. If the growth mart is not deployed, the loader uses fact-derived monthly totals
as a fallback. Fact totals retain their original
precision; the existing mart rounds its segment revenue. No dbt rebuild is needed.

- QoQ compares the latest selected calendar quarter with the immediately preceding quarter.
- YoY compares the latest selected year with the prior year, using the same quarter when selected.
- Rolling 30-Day Run Rate means trailing 30-calendar-day revenue, not an annualized projection. The SQL RANGE window ends at the latest selected sales date; insufficient initial history shows unavailable.
- Peak Seasonality Multiplier is maximum / mean revenue over selected year-months with sales.
- Avg Daily Order Velocity is distinct channel/order invoices divided by active sales dates, not order-line rows or all calendar days.

Historical baselines retain channel/category/subcategory selections and expand
date scope only. Missing or nonpositive comparison denominators show unavailable.
Partial periods use available totals rather than pretending to be matched YTD.
