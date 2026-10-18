# AdventureWorks Analytics design system

Approved direction: a light internal data console inspired by the supplied
Lakebase screenshot. Original AdventureWorks branding; no copied vendor assets.

- Background #F5F7FA; white surfaces; text #243B45; muted #596B78.
- Primary #2274B5; secondary chart series #138579; borders #DFE6ED.
- System sans-serif, 16px base, compact 13–14px controls, 28px page headings.
- 8px spacing basis and card radius; 24px card gaps; restrained shadows.
- Header 72px; desktop sidebar 248px expanded / 72px collapsed.
- Mobile breakpoint 768px; accessible modal navigation drawer below it.
- White bordered cards, thin grid lines, blue/teal charts with legends.
- Explicit demo labels; no controls that imply a real connection or pipeline run.
- Visible keyboard focus; labeled icon controls; reduced motion support.
- Sidebar workspace names wrap naturally without ellipsis or a line clamp. Break
  unspaced names only as needed. Keep the collapse control beside the Workspace
  label, separate from the identity card; retain the control in collapsed mode.

The UI UX Pro Max search matched data-dense dashboard styling and keyboard
navigation guidance. Its unrelated enterprise marketing/landing-page pattern
was rejected; the reference and approved console plan govern layout and color.
Dash is not among its stack presets; implementation follows Dash APIs and the
repository conventions. Runtime visual constants are centralized in theme.py.

Executive monthly chart: blue gross revenue bars on the left USD axis and a
teal gross profit margin line with markers on the right percentage axis. Compute
monthly margin from summed profit / summed revenue, respecting all five filters.
Use exact-value hover labels and a legend; zero-revenue margins are gaps.
The executive monthly card defaults to the original revenue line chart. An
upper-right three-dot menu switches between Revenue line and Revenue + margin,
with the choice persisted locally in the browser. The menu supports keyboard
activation, Escape dismissal, outside-click dismissal, and focus restoration.
The revenue breakdown card defaults to the original Revenue by channel bar chart.
Its three-dot menu also offers a blue/teal channel-share donut labeled B2C Internet
and B2B Reseller, and a category/subcategory revenue treemap, with a separate
browser-local preference. Both use
filtered revenue, exact hover amounts, and share labels; the product detail table
provides the tabular breakdown. Empty or negative share data has an explicit state.
Executive KPIs include filter-aware YoY badges. Compare a selected calendar year
(and quarter, if selected) to the prior year with the same channel and product
filters. Show percent changes for amounts/counts and percentage-point changes
for margin. All-years selections prompt for a year; missing periods and zero
baselines show neutral states. Direction arrows accompany color. Hover text
identifies the compared calendar periods and exact values; periods use available
totals, not an implied matched year-to-date cutoff.

## Dark appearance

Light is the default for new browsers; System follows the device appearance only
when explicitly selected. Opening Settings never saves or changes appearance.
The dark appearance adapts the existing console using the installed
[dark-mode-design-expert](../../.agents/skills/dark-mode-design-expert/SKILL.md)
from `curiositech/some_claude_skills`. Keep the existing layout and blue/teal identity.

- `theme.py` owns semantic CSS/Plotly tokens: navy background `#0c1222`, surface
  `#121a2e`, raised cards `#192339`, and overlay menus/modals `#22304a`.
- Use off-white `#f1f5f9` primary text, `#94a3b8` muted text, brighter blue
  `#60a5fa` and teal `#2dd4bf`. Dark ink belongs on bright primary buttons.
- Decorative dividers use `--border`; interactive boundaries use
  `--control-border` for at least 3:1 contrast against all dark surfaces.
- Apply browser-local `display-preferences` before CSS on every page shell.
  Observe system appearance changes only when the preference is System, and
  synchronize changes across tabs. Explicit Light/Dark overrides the system.
- Prefer tonal surface elevation for cards, dropdowns and dialogs. Retain visible
  focus, status labels, chart series distinctions and reduced-motion behavior.
- Restyle chart layout after render and filter updates, preserving series data,
  axis ranges, chart choice and zoom. Never run warehouse loaders for theme changes.

## Chart feedback

All chart cards retain a `dcc.Loading` wrapper and a polite, atomic status region
immediately after the plot. Use `chart_feedback.py` to keep empty/error messages
in that shared position, clear stale feedback when data returns, and distinguish
measured zero from unavailable data. Empty status regions occupy no space.

Hide routine successful-load messages. Keep notes that change interpretation,
including comparison baselines, lifecycle/age dates, top-N limits, retail-only
scope, map boundaries, and explicit synthetic-data disclosures. Chart changes
must not add warehouse queries or alter filter/query/cache contracts.
