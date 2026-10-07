"""Phase-one workspace overview: illustrative content, no warehouse access."""

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html
from components import card, heading, icon

dash.register_page(
    __name__, path="/workspace", title="Workspace Overview | AdventureWorks"
)

SAVED_VIEWS = (
    (
        "finance",
        "Annual Revenue Review",
        "Revenue & Sales",
        "Finance",
        ("2013", "All Channels", "All Products"),
    ),
    (
        "marketing",
        "Regional Expansion Opportunities",
        "Customers & Regions",
        "Marketing",
        ("2013", "Internet", "North America"),
    ),
    (
        "supply",
        "Wholesale Fulfillment Watch",
        "Wholesale & Resellers",
        "Supply Chain",
        ("2013 · Q4", "Reseller", "Bikes"),
    ),
)
DEFINITIONS = (
    (
        "Gross Revenue",
        "Sum of sales amounts",
        "Revenue for the selected calendar period, sales channel, and products. Currency: USD.",
    ),
    (
        "Gross Profit Margin",
        "Gross profit ÷ Gross revenue × 100",
        "Margin uses summed profit and revenue. A zero-revenue period has no defined margin.",
    ),
    (
        "Average Order Value",
        "Revenue ÷ Distinct orders",
        "Average revenue per invoice in the selected sales period. Invoice lines count together as one order.",
    ),
    (
        "Avg Customer Value",
        "Cumulative retail revenue ÷ Acquired profiles",
        "Measured through the reporting cutoff. Product filters select historical purchasers of those products.",
    ),
    (
        "Customer Churn Rate",
        "Dormant profiles ÷ Customer base × 100",
        "Dormant means over 180 days without a retail order, measured at the reporting cutoff rather than today.",
    ),
    (
        "MoM Growth",
        "(Current − Previous) ÷ Previous × 100",
        "Compares consecutive calendar months with matching product and channel filters. Missing or nonpositive baselines show an unavailable state.",
    ),
)


def sample_badge(text="Sample"):
    return dbc.Badge(text, color=None, className="badge workspace-sample")


def section(title, children, identifier, extra=None):
    result = card(title, children, extra)
    result.id = identifier
    return result


def saved_cards(team="all"):
    return [
        html.Details(
            [
                html.Summary(
                    [
                        html.Span(icon("dashboard"), className="workspace-view-icon"),
                        html.Div(
                            [
                                html.Strong(name),
                                html.Small(f"{report} · {owner}"),
                                html.Div(
                                    [
                                        html.Span(tag, className="workspace-tag")
                                        for tag in tags
                                    ],
                                    className="workspace-tags",
                                ),
                            ],
                            className="workspace-view-content",
                        ),
                        icon("chevron"),
                    ]
                ),
                html.P(
                    "Sample saved view · These filters are illustrative. Saving and restoring report filters will be added in a later phase.",
                    className="workspace-view-note",
                ),
            ],
            className="workspace-view",
        )
        for group, name, report, owner, tags in SAVED_VIEWS
        if team == "all" or team == group
    ]


def definition_cards(search=""):
    query = (search or "").strip().casefold()
    matched = [item for item in DEFINITIONS if query in " ".join(item).casefold()]
    if not matched:
        return html.P(
            "No matching metrics. Try revenue or customer.",
            className="muted",
            role="status",
        )
    return [
        html.Details(
            [
                html.Summary([label, icon("chevron")]),
                html.Div(
                    [html.Code(formula), html.P(description)],
                    className="workspace-definition-body",
                ),
            ],
            open=label == "Gross Revenue",
            className="workspace-definition",
        )
        for label, formula, description in matched
    ]


def layout():
    summary = section(
        "Workspace Summary",
        [
            html.Dl(
                [
                    html.Div([html.Dt(label), html.Dd(value)])
                    for label, value in (
                        ("Workspace", "AdventureWorks Analytics"),
                        ("Owner", "Sample Workspace Owner"),
                        ("Purpose", "Sales & Customer Intelligence"),
                        ("Access", "Internal Business Team · Sample"),
                    )
                ],
                className="workspace-summary-details",
            )
        ],
        "workspace-summary",
        sample_badge(),
    )
    freshness = section(
        "Data Freshness",
        [
            html.Div(
                [
                    html.Div([html.Small(label), html.Strong(value), html.Span(note)])
                    for label, value, note in (
                        (
                            "Last Successful Refresh",
                            "Oct 7, 8:30 PM",
                            "2026 · Asia/Manila",
                        ),
                        (
                            "Latest Sales Date",
                            "Jan 28, 2014",
                            "Historical dataset · Sample",
                        ),
                        (
                            "Report Coverage",
                            "4 Reports",
                            "Revenue, wholesale, growth, customers",
                        ),
                    )
                ],
                className="workspace-freshness-stats",
            ),
            html.Div(
                [
                    html.Small("Illustrative values · No live connection"),
                    dcc.Link("View Monitoring →", href="/monitoring"),
                ],
                className="workspace-card-footer",
            ),
        ],
        "workspace-freshness",
        sample_badge("Sample · Complete"),
    )
    saved = section(
        "Saved Views",
        [
            html.P(
                "Resume an analysis with its filters ready.",
                className="muted workspace-subtitle",
            ),
            dcc.RadioItems(
                id="workspace-view-team",
                options=[
                    dict(label="All Views", value="all"),
                    dict(label="Finance", value="finance"),
                    dict(label="Marketing", value="marketing"),
                    dict(label="Supply Chain", value="supply"),
                ],
                value="all",
                className="workspace-view-tabs",
                inline=True,
            ),
            html.Div(saved_cards(), id="workspace-saved-cards"),
        ],
        "workspace-saved-views",
        html.Span("3 Sample Views", id="workspace-view-count", className="badge"),
    )
    quality = section(
        "Data Quality Notices",
        [
            html.P(
                "Sample context for interpreting reports.",
                className="muted workspace-subtitle",
            ),
            *[
                html.Article(
                    [
                        sample_badge(status),
                        html.H3(title),
                        html.P(description),
                        html.Details([html.Summary("View Context"), html.P(context)]),
                    ],
                    className="workspace-notice",
                )
                for status, title, description, context in (
                    (
                        "Sample · Review",
                        "Source Cost Anomalies",
                        "Some product lines may show negative gross profit. Review source costs before making margin decisions.",
                        "Illustrative notice: source cost anomalies may affect Jerseys and Touring Frames. This sample is not a current data-quality assessment.",
                    ),
                    (
                        "Sample · Coverage",
                        "Incomplete State / Province Coverage",
                        "Territory totals can include revenue with no mapped state or province.",
                        "Illustrative notice: unlocated reseller or unknown geography remains in territory totals. The map should disclose unmapped revenue.",
                    ),
                )
            ],
        ],
        "workspace-quality",
        sample_badge("2 Sample Notices"),
    )
    definitions = section(
        "Metric Definitions",
        [
            html.P(
                "A shared understanding of the numbers.",
                className="muted workspace-subtitle",
            ),
            html.Label(
                "Search Metric Definitions",
                htmlFor="workspace-metric-search",
                className="workspace-sr-only",
            ),
            dcc.Input(
                id="workspace-metric-search",
                type="search",
                placeholder="Search metrics…",
                value="",
                debounce=False,
                className="workspace-search",
            ),
            html.Div(definition_cards(), id="workspace-definition-list"),
            html.Small(
                "Illustrative glossary · Phase-one preview",
                className="workspace-glossary-note",
            ),
        ],
        "workspace-definitions",
        sample_badge(),
    )
    quick = section(
        "Quick Links",
        [
            html.Div(
                [
                    dcc.Link(
                        [
                            icon(key),
                            html.Div([html.Strong(label), html.Small(description)]),
                        ],
                        href=path,
                        className="workspace-quick-link",
                    )
                    for key, label, description, path in (
                        ("dashboard", "Reports", "Explore performance", "/dashboard"),
                        ("monitoring", "Monitoring", "Pipeline history", "/monitoring"),
                        ("tables", "Tables", "Browse data", "/tables"),
                        ("settings", "Settings", "Display preferences", "/settings"),
                    )
                ],
                className="workspace-quick-links",
            )
        ],
        "workspace-quick-links",
    )
    return html.Div(
        [
            heading(
                "Workspace Overview",
                "Your reports, data context, and saved analysis in one place.",
                html.A(
                    "Saved Views",
                    href="#workspace-saved-views",
                    className="button primary",
                ),
            ),
            html.Div(
                sample_badge("Phase 1 · Mock Data"), className="workspace-preview-label"
            ),
            html.Nav(
                [
                    html.A(label, href=f"#{target}")
                    for label, target in (
                        ("Overview", "workspace-summary"),
                        ("Saved Views", "workspace-saved-views"),
                        ("Data Quality", "workspace-quality"),
                        ("Metric Definitions", "workspace-definitions"),
                        ("Quick Links", "workspace-quick-links"),
                    )
                ],
                className="workspace-section-nav",
                **{"aria-label": "Workspace page sections"},
            ),
            html.Div([summary, freshness], className="workspace-top-grid"),
            html.Div(
                [
                    html.Div([saved, quality], className="workspace-stack"),
                    html.Div([definitions, quick], className="workspace-stack"),
                ],
                className="workspace-content-grid",
            ),
            html.P(
                "Phase-one preview · Workspace details, freshness, saved views, and quality notices are sample content.",
                className="workspace-preview-footer",
            ),
        ],
        className="workspace-page",
    )


@callback(
    Output("workspace-saved-cards", "children"),
    Output("workspace-view-count", "children"),
    Input("workspace-view-team", "value"),
)
def filter_saved_views(team):
    selected = team if team in {"all", "finance", "marketing", "supply"} else "all"
    cards = saved_cards(selected)
    return cards, f"{len(cards)} Sample {'View' if len(cards) == 1 else 'Views'}"


@callback(
    Output("workspace-definition-list", "children"),
    Input("workspace-metric-search", "value"),
)
def search_definitions(search):
    return definition_cards(search)
