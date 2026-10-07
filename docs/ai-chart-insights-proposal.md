# AI Insights Below Dashboard Charts

Status: Future idea — not approved for implementation yet.

## Purpose

Add a short, understandable AI-generated insight beneath each chart in the
AdventureWorks Analytics dashboard. The idea comes from the explanatory text
below the geographic map: help people understand the displayed data and identify
what deserves attention without requiring them to interpret the visualization
on their own.

When this brief is uploaded for future work, first confirm the implementation
scope and inspect the current application. This document describes a proposal;
it does not authorize deployment, spending, or sharing warehouse data with an
external AI provider.

## Suggested First Release

Start with the Geographic Map on the Customers & Regions page. Evaluate its
usefulness and accuracy before expanding to the other charts on Customers &
Regions, Executive Revenue & Sales Performance, B2B Wholesale & Reseller
Analytics, and Time-Series Growth & Seasonal Dynamics.

Preserve the existing charts, filters, three-dot chart menus, and layout. Add an
**AI Insight** section directly below the active chart, inside its card.

## User Experience

- Show one or two plain-language sentences identifying a meaningful pattern,
  comparison, concentration, or change in the displayed data.
- Explain why the observation may matter, without inventing causes or asserting
  that a recommended action will produce a particular result.
- Update the insight when the chart type, relevant filters, reporting period,
  or geographic drill-down changes.
- Keep loading independent of the chart so AI generation never delays data
  rendering. Show a small loading indicator in the insight area.
- Do not display an old insight as though it applies to newly selected filters.
- For empty or insufficient data, display a brief factual message instead of
  generating speculation. For AI service failures, use a deterministic summary
  or an unobtrusive unavailable state.
- Keep the section responsive, readable, and accessible; avoid long paragraphs
  and overflow. Label generated content clearly as **AI Insight**.

## Illustrative Output

The following example describes wording, not a verified current result:

> California leads retail revenue at $5.71M. Compare its customer count and
> average customer value with other states to assess whether its lead reflects
> a larger customer base or higher spending per customer.

Only include the second sentence if the relevant comparison metrics are
available or the dashboard provides an appropriate way to inspect them.

## Data and Accuracy Requirements

Analyze the aggregated data behind the active chart, rather than asking the AI
to infer numerical values from a screenshot. Supply only the minimum necessary:

- Chart title, type, axis meanings, units, and metric definitions.
- Active filters, reporting cutoff, and selected geographic scope.
- The aggregated series or a bounded statistical summary of that series.
- Relevant caveats, such as partial periods, missing geography, unavailable
  baselines, and whether a metric is cumulative or period-specific.

Compute exact rankings, totals, percentages, differences, and comparisons in
Python or SQL. Use the AI primarily to explain those verified calculations.
Require statements to be supported by the supplied data; validate numerical
claims before showing them where feasible.

Do not infer causation, demographics, customer intent, campaign success, or
operational problems that the data does not establish. Do not imply that a
cross-sectional lifecycle funnel measures cohort conversion. Do not equate
revenue with profit or a reseller's annual revenue attribute with its purchases
in the filtered period.

## Proposed Dash Integration

- Reuse the existing warehouse loaders, aggregation functions, and metric
  definitions; avoid a second query solely to obtain the same chart data.
- Generate insights server-side in a separate callback or background job using
  the application's supported callback infrastructure.
- Generate only for the active chart option. Debounce rapid filter changes and
  discard responses that no longer match the displayed chart's context.
- Keep client state lightweight. Do not send raw customer records or large
  datasets through `dcc.Store`.
- Cache by chart identity, normalized filters, drill-down scope, data freshness,
  metric-definition/prompt version, and model configuration. Respect access
  boundaries when reusing cached results.
- Set bounded input/output sizes, timeouts, concurrency limits, and a sensible
  retry policy. Avoid repeated generation for unchanged data and filters.
- Render the insight as plain text or a restricted safe format, not arbitrary
  model-generated HTML.

## Privacy, Security, and Cost

Choose a provider and model when implementation begins. Confirm permitted data
handling before sending warehouse aggregates to any external service; aggregate
data can still be confidential. Exclude personal identifiers, individual
customer records, credentials, and unnecessary business details.

Keep API credentials server-side. Treat chart labels and warehouse text as
untrusted data, never as instructions to the model. Preserve the application's
authentication and authorization checks for generation and cached results.

Agree on a usage budget, rate limits, retention policy, and operational logging
that avoids exposing sensitive payloads. Automatic generation versus an explicit
“Generate Insight” action remains a decision for the pilot.

## Validation and Acceptance Criteria

- Insights match the active chart, filters, period, units, and drill-down scope.
- Every numerical claim agrees with the supplied verified calculations.
- Empty data, ties, zero baselines, partial periods, and missing geography are
  handled without misleading statements.
- Filter changes during generation cannot attach a stale response to a new view.
- Cached results respect data freshness and access boundaries.
- Service errors and timeouts do not break or block the dashboard.
- Desktop and mobile layouts remain readable and contained within chart cards.
- Human review of representative outputs finds the explanations useful,
  concise, and appropriately cautious about causes.

## Decisions to Make When Resuming

1. Confirm a geographic-map pilot or a broader initial scope.
2. Choose the AI provider/model and approve the data that may be sent to it.
3. Choose automatic generation or user-triggered generation, with cost limits.
4. Agree on insight freshness, caching, and the fallback experience.
5. Review the pilot before rolling it out to additional charts.
