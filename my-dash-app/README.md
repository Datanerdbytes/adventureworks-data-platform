# AdventureWorks Analytics — local demo

A four-page Dash console with a collapsible sidebar, responsive mobile drawer,
Plotly charts, and searchable AG Grid tables. All records are deterministic,
synthetic examples from September 2026. Refresh updates the display timestamp,
not the fixture period. No database, dbt jobs, or network data loaders are used. The public landing
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

“Sign in” and “Open workspace” open `/dashboard` and use the browser's native
username/password prompt. Missing configuration returns 503; invalid credentials
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
