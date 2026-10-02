import dash
from dash import Input, Output, callback, dcc, html
import plotly.express as px
from components import card, details, graph, heading, metric
from analytics import REPORTS
from data import activity, runs
from theme import TOKENS, style_figure

dash.register_page(__name__, path="/dashboard", title="Dashboard | AdventureWorks")


def layout():
    return html.Div(
        [
            heading(
                "Project dashboard",
                "A clear view of your analytics workspace.",
                dcc.Link(
                    "Explore tables →", href="/tables", className="button primary"
                ),
            ),
            html.Div(
                [
                    dcc.Link(
                        [
                            html.Span(f"0{index + 1}", className="report-number"),
                            html.Strong(title),
                            html.Small(description),
                            html.Span("Open report →", className="report-action"),
                        ],
                        href=f"/dashboard/{kind}",
                        className="report-launcher",
                    )
                    for index, (kind, (title, _, description)) in enumerate(
                        REPORTS.items()
                    )
                ],
                className="report-launchers",
            ),
            html.Div(id="dashboard-metrics", className="metrics"),
            html.Div(
                [
                    card(
                        "Pipeline activity",
                        [
                            html.P(
                                "Rows processed · September 30, 2026", className="muted"
                            ),
                            graph("dashboard-activity"),
                        ],
                        html.Span("24 hours", className="badge"),
                    ),
                    card(
                        "Project details",
                        [details()],
                        dcc.Link("Settings", href="/settings"),
                    ),
                ],
                className="dashboard-grid",
            ),
            card(
                "Recent pipeline runs",
                [html.Div(id="dashboard-runs")],
                dcc.Link("View monitoring →", href="/monitoring"),
            ),
            html.P(id="dashboard-status", role="status", className="muted"),
        ]
    )


@callback(
    Output("dashboard-activity", "figure"),
    Output("dashboard-metrics", "children"),
    Output("dashboard-runs", "children"),
    Output("dashboard-status", "children"),
    Input("app-location", "pathname"),
)
def populate(path):
    if path != "/dashboard":
        raise dash.exceptions.PreventUpdate
    try:
        frame = activity()
        figure = style_figure(
            px.line(
                frame,
                x="Hour",
                y="Rows processed",
                color="Pipeline",
                color_discrete_sequence=[TOKENS["primary"], TOKENS["teal"]],
            )
        )
        items = runs(days=7)
        metrics = [
            metric(
                "Rows processed",
                f"{frame['Rows processed'].sum():,}",
                "Across two ingestion streams",
            ),
            metric("Pipeline runs", str(len(items)), "In the sample week"),
            metric(
                "Successful runs",
                str(sum(r["Status"] == "Success" for r in items)),
                "Completed without warnings",
            ),
            metric("Sample tables", "3", "Ready to explore"),
        ]
        recent = [
            html.Div(
                [
                    html.Div(
                        [
                            html.Strong(r["Pipeline"]),
                            html.Small(
                                r["Run"] + " · " + r["Started"], className="muted"
                            ),
                        ]
                    ),
                    html.Span(str(r["Duration (s)"]) + " sec", className="muted"),
                    html.Span(r["Status"], className="badge success"),
                ],
                className="run-row",
            )
            for r in sorted(items, key=lambda r: r["Started"], reverse=True)[:3]
        ]
        return figure, metrics, recent, "All values shown are synthetic demo data."
    except (ValueError, KeyError, TypeError):
        return (
            {},
            [],
            [],
            "Unable to display sample activity. Reload the page to retry.",
        )
