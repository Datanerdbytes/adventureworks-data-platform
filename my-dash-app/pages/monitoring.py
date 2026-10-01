from datetime import datetime, timezone
import dash
from dash import Input, Output, callback, dcc, html
import pandas as pd
import plotly.express as px
from components import card, field, graph, grid, heading, metric, icon
from data import PIPELINES, runs, grid_options
from theme import TOKENS, style_figure

dash.register_page(__name__, path="/monitoring", title="Monitoring | AdventureWorks")


def layout():
    return html.Div(
        [
            heading(
                "Monitoring",
                "Follow pipeline health and execution history.",
                html.Button(
                    [icon("refresh"), "Refresh"],
                    id="monitoring-refresh",
                    className="button",
                ),
            ),
            html.Div(
                [
                    field(
                        "Pipeline",
                        dcc.Dropdown(
                            ["All pipelines", *PIPELINES],
                            "All pipelines",
                            id="monitoring-pipeline",
                            clearable=False,
                            persistence=True,
                            persistence_type="session",
                        ),
                    ),
                    field(
                        "Sample window",
                        dcc.Dropdown(
                            [
                                {"label": label, "value": value}
                                for label, value in [
                                    ("Last day", 1),
                                    ("Last 7 days", 7),
                                    ("Last 30 days", 30),
                                ]
                            ],
                            7,
                            id="monitoring-window",
                            clearable=False,
                        ),
                    ),
                ],
                className="filters",
            ),
            html.Div(id="monitoring-metrics", className="metrics three"),
            card("Run duration", [graph("monitoring-chart")]),
            card("Execution history", [grid("monitoring-grid")]),
            html.P(id="monitoring-status", role="status", className="muted"),
        ]
    )


@callback(
    Output("monitoring-chart", "figure"),
    Output("monitoring-grid", "rowData"),
    Output("monitoring-grid", "columnDefs"),
    Output("monitoring-metrics", "children"),
    Output("monitoring-status", "children"),
    Output("monitoring-grid", "dashGridOptions"),
    Input("monitoring-pipeline", "value"),
    Input("monitoring-window", "value"),
    Input("monitoring-refresh", "n_clicks"),
    Input("display-preferences", "data"),
)
def populate(pipeline, days, clicks, preferences):
    try:
        records = runs(pipeline, days)
        if not records:
            return {}, [], [], [], "No sample runs match your filters.", grid_options()
        frame = pd.DataFrame(records).sort_values("Started")
        figure = style_figure(
            px.line(
                frame,
                x="Started",
                y="Duration (s)",
                color="Pipeline",
                markers=True,
                color_discrete_sequence=[TOKENS["primary"], TOKENS["teal"], "#8A659E"],
            )
        )
        metrics = [
            metric("Total runs", str(len(records)), "Selected sample window"),
            metric(
                "Success rate",
                f"{sum(r['Status']=='Success' for r in records)/len(records):.0%}",
                "Synthetic run outcomes",
            ),
            metric(
                "Average duration",
                f"{frame['Duration (s)'].mean():.0f}s",
                "Across selected pipelines",
            ),
        ]
        return (
            figure,
            records,
            [{"field": key} for key in records[0]],
            metrics,
            "Demo snapshot · Refreshed "
            + datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
            grid_options((preferences or {}).get("pageSize", 10)),
        )
    except (ValueError, KeyError, TypeError):
        return (
            {},
            [],
            [],
            [],
            "Unable to load sample runs. Try Refresh.",
            grid_options(),
        )
