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

### Customer and regional KPIs

The combined Customers & Regions page reuses the five warehouse filters and
five individually wrapped loading cards. Both demographic charts use warehouse
data and the same sales filters. Supporting detail remains explicitly synthetic;
the former sample year and region dropdowns have been removed.

Customer base includes distinct profiles acquired by the reporting cutoff,
including dormant customers. Acquisition uses `date_first_purchase`, falling
back to the first recorded retail sale when missing. Product filters restrict
the cohort to historical purchasers of those products. Average customer value
is cumulative matching retail revenue through the cutoff divided by that base.
Churn measures profiles whose last retail order (across all products) was more
than 180 days before the cutoff; where fact history is absent, first-purchase
date is the last known purchase. The cutoff is the selected year/quarter end,
capped at the latest warehouse sale; All uses the latest available sale.

Top Revenue Territory ranks selected-period sales across selected channels.
Top Growth State ranks positive absolute distinct-invoice increases for the
latest reporting month against the immediately preceding calendar month, with
unchanged product/channel filters. Country disambiguates identical state names;
ties sort by state/country. Missing prior-month history shows unavailable growth.
Partial months compare available totals. Reseller has no customer keys and is
not applicable to the four customer-based cards.

The demographic and growth marts discard customer IDs and/or customer-state/date
grain. These non-additive metrics therefore reuse their source facts and dimensions
rather than summing demographic segment counts or inventing missing identities.
Queries are parameterized, cached for 60 seconds, and capped at 100 MiB billed.


The retail region and age charts count distinct customers purchasing within the
selected sales scope, not the cumulative acquired-profile KPI base. Region means
home country from `dim_customer`. Age uses completed years at the latest warehouse
sales date in the selected calendar scope; missing, future, or implausible birth
dates appear as Unknown. Under-18 customers have a separate bucket. Reseller-only
selections show an explicit no-retail-customers state. The query deduplicates
customer profiles before aggregation; no customer-level records reach the browser.

The regional chart's three-dot menu includes a revenue Geographic Map. Select a
sales territory group on the choropleth or in the labeled dropdown to drill into
states/provinces; the dropdown’s All territory groups option returns to the overview. The top mapped state
and its revenue are called out. Geographic revenue follows the demographic mart's
territory-group/country/customer-state grain. Date/product-filtered selections
rebuild that grain from facts; missing marts use the same fallback. Wholesale
and unknown states contribute to territory totals but are reported as unlocated
in state views. Map colors rescale per view. Bundled public-domain Natural Earth
boundaries and warehouse-name aliases are documented in map_data/README.md.

The customer age card's three-dot menu also offers **Customer Lifecycle Funnel
Chart** (`px.funnel`). It uses the same acquired-profile cohort and reporting
cutoff as the customer KPIs. Each customer appears once: New Cohort has at most
one recorded invoice and activity within 90 days; Active Repeat has multiple
invoices and activity within 90 days; Slipping Account last ordered 91–180 days
ago; Dormant last ordered over 180 days ago. Missing order history falls back to
first purchase. Product filters select the historical purchaser cohort; repeat
counts and last activity consider all retail products through the cutoff.
Resellers are excluded. Stages retain their chronological order, including zero
counts, and describe a cross-sectional snapshot, not cohort conversion rates.
Only the selected secondary chart's cached warehouse loader runs.

The right-hand customer chart menu includes **Revenue by Income Tier**,
**Revenue by Occupation Type**, and **Revenue by Education Level**. These
horizontal bars sum filtered retail `fct_sales.sales_amount`, joined to
`dim_customer` and the date/product dimensions. Source `englishoccupation` and
`englisheducation` are normalized to `occupation` and `education_level` in the
warehouse. Income tiers match the demographic mart's <30k, 30k–70k, 70k–100k,
and 100k+ buckets; missing attributes remain Unknown. Income is ordered by tier;
occupation and education are ranked by revenue. All five filters apply, reseller
selections have an explicit empty state, and only the selected view is queried.

The **Granular Customer Demographic & Regional Ledger** replaces customer sample
supporting detail with cached warehouse aggregates. Rows are keyed by home
country and state/province (both appear in the State / Province cell); territory
is mapped from home country to the sales territory dimension. Ambiguous or
missing geography is Unknown. Its acquired-profile cohort, cutoff, cumulative
product-filtered sales and distinct invoice frequency match the customer KPI
contract; dormancy considers all retail products and falls back to first purchase
when order history is absent. Income and occupation modes count each profile
once, resolving tied frequencies with known values before Unknown and then
alphabetically. The eight-column AG Grid supports numeric sorting/filtering,
10-row pagination and CSV export of all filtered/sorted rows with raw numeric
values. The customer page no longer runs the synthetic supporting-detail callback.
