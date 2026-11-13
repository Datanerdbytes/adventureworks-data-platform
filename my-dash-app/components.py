from dash import dcc, html
import dash_ag_grid as dag
import plotly.graph_objects as go
from data import grid_options
from theme import TOKENS


def icon(name):
    return html.Img(
        src=f"/assets/icons/{name}.svg",
        className="icon",
        alt="",
        **{"aria-hidden": "true"},
    )


def heading(title, subtitle, action=None):
    """Page header; actions share one .page-actions group in every header."""
    return html.Div(
        [
            html.Div([html.H1(title), html.P(subtitle, className="muted")]),
            html.Div(action, className="page-actions") if action is not None else None,
        ],
        className="page-heading",
    )


def card(title, children, extra=None):
    return html.Section(
        [html.Div([html.H2(title), extra], className="card-heading"), *children],
        className="card",
    )


def graph(identifier):
    return dcc.Loading(
        dcc.Graph(
            id=identifier,
            figure={"data": [], "layout": {"template": "plotly_white"}},
            config={"displayModeBar": False, "responsive": True},
            className="chart",
        ),
        type="circle",
        parent_className="chart-loading",
    )


def grid(identifier):
    return dcc.Loading(
        dag.AgGrid(
            id=identifier,
            rowData=[],
            columnDefs=[],
            dashGridOptions=grid_options(),
            columnSize="responsiveSizeToFit",
            defaultColDef={
                "filter": True,
                "sortable": True,
                "resizable": True,
                "minWidth": 120,
            },
            className="ag-theme-balham data-grid",
        ),
        type="circle",
    )


def details():
    return html.Dl(
        [
            html.Div([html.Dt(k), html.Dd(v)], className="detail-row")
            for k, v in [
                ("Project", "AdventureWorks"),
                ("Environment", "Local demo"),
                ("Data source", "Synthetic fixtures"),
                ("Sample period", "September 2026"),
                ("Connection", "Offline"),
            ]
        ]
    )


def field(label, child):
    return html.Div([html.Label(label, htmlFor=child.id), child], className="field")


def metric(label, value, note, sparkline=None):
    children = [
        html.Span(label, className="muted"),
        html.Strong(value),
        html.Small(note),
    ]
    if sparkline is not None:
        children.append(
            dcc.Graph(
                figure=sparkline,
                config={"displayModeBar": False, "responsive": True},
                className="metric-sparkline",
            )
        )
    return html.Div(children, className="metric")


def sparkline(x, ys, color, hovertemplate):
    """Tiny transparent-background trend line sized for KPI cards.

    Axes are hidden and zoom is frozen; the caller owns the series data,
    color, and hover wording.
    """
    figure = go.Figure(
        go.Scatter(
            x=x,
            y=ys,
            mode="lines",
            line={"color": color, "width": 1.6},
            connectgaps=False,
            showlegend=False,
            hovertemplate=hovertemplate,
        )
    )
    figure.update_layout(
        margin={"l": 0, "r": 0, "t": 2, "b": 0},
        height=44,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel={"bgcolor": TOKENS["surface"]},
        font={"family": TOKENS["font"], "size": 11, "color": TOKENS["muted"]},
    )
    figure.update_xaxes(visible=False, fixedrange=True)
    figure.update_yaxes(visible=False, fixedrange=True)
    return figure


def ranked_list(rows):
    """Render top-N rows as ranked lines: position, name, share bar, value.

    ``rows`` is a list of dicts with ``name``, ``value`` (preformatted) and an
    optional ``share`` in [0, 1] driving the bar width. Rows without a share
    render the bar track empty; no trend arrows are shown because the loaders
    carry no per-item time series.
    """
    if not rows:
        return html.P(
            "No ranked results for the current filters.",
            className="muted",
            role="status",
            **{"aria-live": "polite", "aria-atomic": "true"},
        )
    items = []
    for position, row in enumerate(rows, start=1):
        share = row.get("share")
        width = 0.0
        if share is not None:
            width = max(0.0, min(1.0, float(share)))
        items.append(
            html.Li(
                [
                    html.Span(f"{position}", className="ranked-rank"),
                    html.Div(
                        [
                            html.Span(row["name"], className="ranked-name"),
                            html.Span(
                                html.Span(
                                    className="ranked-bar",
                                    style={"width": f"{width * 100:.0f}%"},
                                ),
                                className="ranked-track",
                            ),
                        ],
                        className="ranked-main",
                    ),
                    html.Span(row["value"], className="ranked-value"),
                ],
                className="ranked-row",
            )
        )
    return html.Ol(items, className="ranked-list")
