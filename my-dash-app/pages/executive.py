"""One consistent set of warehouse filters for the executive report."""

import logging
import dash
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Input, Output, State, callback, clientside_callback, dcc, html
from components import card, field, graph, grid, heading
from data import grid_options
from revenue_kpis import (
    kpi_cards,
    add_yoy_comparison,
    load_filter_catalog,
    load_executive_report,
    warehouse_location,
)
from theme import TOKENS, style_figure

ALL = "__all__"
FILTERS = ("year", "quarter", "channel", "category", "subcategory")
dash.register_page(
    __name__,
    path="/dashboard/executive",
    title="Executive Revenue & Sales Performance | AdventureWorks",
)


def dropdown(name, label):
    return field(
        label,
        dcc.Dropdown(
            id=f"executive-{name}",
            options=[{"label": "All", "value": ALL}],
            value=ALL,
            clearable=False,
        ),
    )


def layout():
    return html.Div(
        [
            heading(
                "Executive Revenue & Sales Performance",
                "Warehouse metrics, trends, and product performance in one view.",
                dcc.Link("← Dashboard overview", href="/dashboard", className="button"),
            ),
            dcc.Store(id="executive-filter-catalog"),
            dcc.Store(id="executive-filter-load", data=True),
            html.Div(
                [
                    html.Div(
                        [
                            dropdown("year", "Calendar year"),
                            dropdown("quarter", "Quarter"),
                        ],
                        className="executive-time-filter",
                    ),
                    dropdown("channel", "Sales channel"),
                    dropdown("category", "Product category"),
                    dropdown("subcategory", "Product subcategory"),
                ],
                className="executive-global-filters",
            ),
            html.P(
                "Filters apply to all five KPIs, both charts, and the detail table. Dates use calendar periods, not fiscal periods.",
                className="muted",
            ),
            html.P(id="executive-filter-status", role="status", className="muted"),
            dcc.Loading(
                html.Div(
                    [
                        html.Div(
                            kpi_cards(note="Loading warehouse data…"),
                            id="executive-live-kpis",
                            className="metrics executive-kpis",
                        ),
                        html.Div(
                            [
                                card(
                                    html.Span(
                                        "Revenue by month", id="executive-chart-title"
                                    ),
                                    [graph("executive-primary")],
                                    html.Details(
                                        [
                                            html.Summary(
                                                "•••",
                                                title="Choose monthly chart",
                                                **{
                                                    "aria-label": "Choose monthly chart"
                                                },
                                            ),
                                            html.Div(
                                                [
                                                    html.Span(
                                                        "Chart type", className="muted"
                                                    ),
                                                    dcc.RadioItems(
                                                        id="executive-chart-type",
                                                        options=[
                                                            {
                                                                "label": "Revenue line",
                                                                "value": "line",
                                                            },
                                                            {
                                                                "label": "Revenue + margin",
                                                                "value": "dual",
                                                            },
                                                        ],
                                                        value="line",
                                                        persistence=True,
                                                        persistence_type="local",
                                                    ),
                                                ],
                                                className="chart-type-options",
                                            ),
                                        ],
                                        className="chart-type-menu",
                                    ),
                                ),
                                card(
                                    html.Span(
                                        "Revenue by channel",
                                        id="executive-breakdown-title",
                                    ),
                                    [graph("executive-secondary")],
                                    html.Details(
                                        [
                                            html.Summary(
                                                "•••",
                                                title="Choose revenue breakdown",
                                                **{
                                                    "aria-label": "Choose revenue breakdown"
                                                },
                                            ),
                                            html.Div(
                                                [
                                                    html.Span(
                                                        "Chart type", className="muted"
                                                    ),
                                                    dcc.RadioItems(
                                                        id="executive-breakdown-type",
                                                        options=[
                                                            {
                                                                "label": "Revenue by channel · Bars",
                                                                "value": "bar",
                                                            },
                                                            {
                                                                "label": "Channel split · Donut",
                                                                "value": "donut",
                                                            },
                                                            {
                                                                "label": "Product mix · Treemap",
                                                                "value": "treemap",
                                                            },
                                                        ],
                                                        value="bar",
                                                        persistence="channel-views-v2",
                                                        persistence_type="local",
                                                    ),
                                                ],
                                                className="chart-type-options",
                                            ),
                                        ],
                                        className="chart-type-menu",
                                    ),
                                ),
                            ],
                            className="report-charts",
                        ),
                        card(
                            "Product performance",
                            [grid("executive-detail")],
                            html.Span("Warehouse data · USD", className="badge"),
                        ),
                        html.P(
                            id="executive-kpi-status", role="status", className="muted"
                        ),
                    ]
                ),
                type="circle",
            ),
        ],
        className="analytics-report",
    )


def options(rows, column):
    return [{"label": "All", "value": ALL}] + [
        {"label": str(value), "value": value}
        for value in sorted({row[column] for row in rows if row[column] is not None})
    ]


@callback(
    Output("executive-filter-catalog", "data"),
    *[Output(f"executive-{name}", "options") for name in FILTERS[:-1]],
    Output("executive-filter-status", "children"),
    Input("executive-filter-load", "data"),
)
def populate_filters(_):
    try:
        rows = load_filter_catalog(*warehouse_location())
        return (
            rows,
            *[
                options(rows, col)
                for col in (
                    "calendar_year",
                    "calendar_quarter_name",
                    "sales_channel",
                    "product_category",
                )
            ],
            "",
        )
    except Exception:
        logging.getLogger(__name__).warning("Executive filter catalog unavailable")
        return (
            None,
            *[[{"label": "All", "value": ALL}]] * 4,
            "Unable to load warehouse filters. Reload this page to retry.",
        )


clientside_callback(
    """function(category, catalog, current) {
    const all = '__all__';
    const allowed = [...new Set((catalog || []).filter(r => category === all || r.product_category === category)
       .map(r => r.product_subcategory).filter(x => x !== null))].sort();
    return [[{label:'All',value:all},...allowed.map(v=>({label:v,value:v}))],
       allowed.includes(current) ? current : all];
}""",
    Output("executive-subcategory", "options"),
    Output("executive-subcategory", "value"),
    Input("executive-category", "value"),
    Input("executive-filter-catalog", "data"),
    State("executive-subcategory", "value"),
)


def normalize_filters(catalog, year, quarter, channel, category, subcategory):
    values = [
        None if value in (None, ALL) else value
        for value in (year, quarter, channel, category, subcategory)
    ]
    for value, column in zip(
        values,
        (
            "calendar_year",
            "calendar_quarter_name",
            "sales_channel",
            "product_category",
            "product_subcategory",
        ),
    ):
        if value is not None and value not in {r[column] for r in catalog}:
            raise ValueError("Invalid selection")
    if (
        values[3] is not None
        and values[4] is not None
        and not any(
            r["product_category"] == values[3] and r["product_subcategory"] == values[4]
            for r in catalog
        )
    ):
        # The category changed before the dependent dropdown reset reached us.
        raise dash.exceptions.PreventUpdate
    return values


def revenue_breakdown(channels, detail, chart_type="bar"):
    if chart_type not in ("donut", "treemap"):
        return style_figure(
            px.bar(
                channels,
                x="sales_channel",
                y="revenue",
                color="sales_channel",
                labels={"revenue": "Revenue (USD)", "sales_channel": "Sales channel"},
                color_discrete_map={
                    "Internet": TOKENS["primary"],
                    "Reseller": TOKENS["teal"],
                },
            )
        )
    if chart_type == "treemap":
        data = pd.DataFrame(detail)
        if not data.empty:
            data["revenue"] = data["revenue"].astype(float)
            data[["product_category", "product_subcategory"]] = data[
                ["product_category", "product_subcategory"]
            ].fillna("Unknown")
            data = data.groupby(
                ["product_category", "product_subcategory"], as_index=False
            )["revenue"].sum()
        amount = data["revenue"] if not data.empty else pd.Series(dtype=float)
    else:
        data = channels.copy()
        amount = data["revenue"]
    # Area charts cannot honestly represent negative revenue contributions.
    if amount.empty or (amount < 0).any() or amount.sum() <= 0:
        figure = style_figure(go.Figure())
        figure.add_annotation(
            text=(
                "No positive revenue to display"
                if not (amount < 0).any()
                else "Negative revenue cannot be shown as shares; see detail table"
            ),
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
        figure.update_xaxes(visible=False)
        figure.update_yaxes(visible=False)
        return figure
    data = data.loc[amount > 0].copy()
    if chart_type == "treemap":
        figure = px.treemap(
            data,
            path=[
                px.Constant("All products"),
                "product_category",
                "product_subcategory",
            ],
            values="revenue",
            color="product_category",
            color_discrete_sequence=[
                TOKENS["primary"],
                TOKENS["teal"],
                "#8064A2",
                "#C58636",
                "#657D94",
            ],
        )
        figure.update_traces(
            textinfo="label+percent root",
            hovertemplate="%{label}<br>Revenue: $%{value:,.2f}<br>Share of selected revenue: %{percentRoot:.1%}<extra></extra>",
            marker_line_width=2,
        )
    else:
        data["Channel"] = data["sales_channel"].replace(
            {"Internet": "B2C Internet", "Reseller": "B2B Reseller"}
        )
        figure = px.pie(
            data,
            names="Channel",
            values="revenue",
            hole=0.62,
            color="Channel",
            color_discrete_map={
                "B2C Internet": TOKENS["primary"],
                "B2B Reseller": TOKENS["teal"],
            },
        )
        figure.update_traces(
            textinfo="percent",
            sort=False,
            hovertemplate="%{label}<br>Revenue: $%{value:,.2f}<br>Share: %{percent:.1%}<extra></extra>",
            marker_line={"color": "white", "width": 2},
        )
    if chart_type == "donut":
        total = float(data["revenue"].sum())
        total_label = f"${total:,.2f}"
        for divisor, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if total >= divisor:
                total_label = f"${total / divisor:.2f}{suffix}"
                break
        figure.add_annotation(
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            text=f"<b>{total_label}</b><br><span style='font-size:12px'>Total sales · USD</span>",
            showarrow=False,
            align="center",
            font={"size": 22, "color": TOKENS["text"]},
            hovertext=f"Total sales: ${total:,.2f} USD · Current filters",
        )
    figure = style_figure(figure)
    figure.update_layout(
        margin={"l": 10, "r": 10, "t": 25, "b": 50},
        legend={"x": 0.5, "xanchor": "center", "y": -0.08, "yanchor": "top"},
    )
    return figure


def render_report(values, chart_type="line", breakdown_type="bar"):
    monthly = pd.DataFrame([dict(row) for row in values["monthly"]])
    if monthly.empty:
        blank = {
            "data": [],
            "layout": {
                "template": "plotly_white",
                "annotations": [
                    {
                        "text": "No data for this selection",
                        "showarrow": False,
                        "xref": "paper",
                        "yref": "paper",
                        "x": 0.5,
                        "y": 0.5,
                    }
                ],
            },
        }
        return (
            kpi_cards(values, "No matching sales · USD"),
            blank,
            blank,
            [],
            "No warehouse sales match the selected filters.",
        )
    monthly["Date"] = pd.to_datetime(
        monthly["calendar_year"].astype(str)
        + "-"
        + monthly["month_name"].str.strip()
        + "-01",
        format="%Y-%B-%d",
    )
    monthly["revenue"] = monthly["revenue"].astype(float)
    monthly["profit"] = monthly["profit"].astype(float)
    trend = (
        monthly.groupby("Date", as_index=False)[["revenue", "profit"]]
        .sum()
        .sort_values("Date")
    )
    margin = [
        profit / revenue * 100 if revenue != 0 else None
        for revenue, profit in zip(trend["revenue"], trend["profit"])
    ]
    channels = monthly.groupby("sales_channel", as_index=False)["revenue"].sum()
    first = make_subplots(specs=[[{"secondary_y": True}]])
    first.add_trace(
        go.Bar(
            x=trend["Date"],
            y=trend["revenue"],
            name="Gross revenue",
            marker_color=TOKENS["primary"],
            hovertemplate="%{x|%b %Y}<br>Gross revenue: $%{y:,.2f}<extra></extra>",
        ),
        secondary_y=False,
    )
    first.add_trace(
        go.Scatter(
            x=trend["Date"],
            y=margin,
            name="Gross profit margin",
            mode="lines+markers",
            connectgaps=False,
            line={"color": TOKENS["teal"], "width": 3},
            hovertemplate="%{x|%b %Y}<br>Gross profit margin: %{y:.2f}%<extra></extra>",
        ),
        secondary_y=True,
    )
    first = style_figure(first)
    first.update_yaxes(
        title_text="Gross revenue (USD)",
        tickprefix="$",
        tickformat="~s",
        rangemode="tozero",
        secondary_y=False,
    )
    first.update_yaxes(
        title_text="Gross profit margin (%)",
        ticksuffix="%",
        showgrid=False,
        zeroline=False,
        rangemode="tozero",
        secondary_y=True,
    )
    first.update_layout(
        margin={"l": 65, "r": 65, "t": 65, "b": 45},
        legend={"y": 1.04, "yanchor": "bottom", "x": 0},
        bargap=0.25,
    )
    if chart_type != "dual":
        first = style_figure(
            px.line(
                trend,
                x="Date",
                y="revenue",
                markers=True,
                labels={"revenue": "Revenue (USD)"},
                color_discrete_sequence=[TOKENS["primary"]],
            )
        )
        first.update_traces(
            hovertemplate="%{x|%b %Y}<br>Gross revenue: $%{y:,.2f}<extra></extra>"
        )
    second = revenue_breakdown(channels, values["detail"], breakdown_type)
    for figure in (first, second):
        figure.update_layout(height=340)
    detail = [
        {
            "Category": row["product_category"],
            "Subcategory": row["product_subcategory"],
            "Revenue (USD)": round(float(row["revenue"]), 2),
            "Gross profit (USD)": round(float(row["profit"]), 2),
            "Units sold": int(row["units"]),
        }
        for row in values["detail"]
    ]
    return (
        kpi_cards(values, note=None),
        first,
        second,
        detail,
        f"BigQuery · Fetched {values['fetched_at']} · Cached for up to 60 seconds. Orders count distinct channel/order pairs. AOV is selected-product revenue per purchasing order.",
    )


@callback(
    Output("executive-live-kpis", "children"),
    Output("executive-primary", "figure"),
    Output("executive-secondary", "figure"),
    Output("executive-detail", "rowData"),
    Output("executive-detail", "columnDefs"),
    Output("executive-detail", "dashGridOptions"),
    Output("executive-kpi-status", "children"),
    Input("executive-filter-catalog", "data"),
    *[Input(f"executive-{name}", "value") for name in FILTERS],
    Input("display-preferences", "data"),
    Input("executive-chart-type", "value"),
    Input("executive-breakdown-type", "value"),
)
def populate_report(
    catalog,
    year,
    quarter,
    channel,
    category,
    subcategory,
    preferences,
    chart_type="line",
    breakdown_type="bar",
):
    columns = [
        {"field": name}
        for name in (
            "Category",
            "Subcategory",
            "Revenue (USD)",
            "Gross profit (USD)",
            "Units sold",
        )
    ]
    settings = grid_options((preferences or {}).get("pageSize", 10))
    if catalog is None:
        return (
            kpi_cards(note="Waiting for warehouse filters"),
            {},
            {},
            [],
            columns,
            settings,
            "Waiting for warehouse filters.",
        )
    try:
        selected = normalize_filters(
            catalog, year, quarter, channel, category, subcategory
        )
        values = load_executive_report(*warehouse_location(), *selected)
        values = add_yoy_comparison(values, *warehouse_location(), *selected)
        cards, first, second, rows, status = render_report(
            values, chart_type, breakdown_type
        )
        return cards, first, second, rows, columns, settings, status
    except dash.exceptions.PreventUpdate:
        raise
    except Exception:
        logging.getLogger(__name__).warning("Executive filtered report unavailable")
        return (
            kpi_cards(note="Warehouse unavailable"),
            {},
            {},
            [],
            columns,
            settings,
            "Unable to load this selection. Change a filter or reload to retry.",
        )


@callback(
    Output("executive-chart-title", "children"), Input("executive-chart-type", "value")
)
def monthly_chart_title(chart_type):
    return (
        "Monthly revenue & gross profit margin"
        if chart_type == "dual"
        else "Revenue by month"
    )


@callback(
    Output("executive-breakdown-title", "children"),
    Input("executive-breakdown-type", "value"),
)
def breakdown_chart_title(chart_type):
    return {
        "donut": "Omnichannel sales split",
        "treemap": "Revenue by category & subcategory",
    }.get(chart_type, "Revenue by channel")
