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
