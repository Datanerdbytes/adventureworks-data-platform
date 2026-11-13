"""One consistent set of warehouse filters for the executive report."""

from chart_feedback import status, feedback

import logging
from datetime import datetime
from typing import Any, Literal
import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Input, Output, State, callback, clientside_callback, dcc, html
from components import card, field, graph, grid, heading, ranked_list
from data import grid_options
from revenue_kpis import (
    MARGIN_HOVERTEMPLATE,
    REVENUE_HOVERTEMPLATE,
    kpi_cards,
    KPI_FIELDS,
    add_yoy_comparison,
    load_filter_catalog,
    load_executive_report,
    margin_percentage,
    monthly_points,
    warehouse_location,
)
from theme import TOKENS, style_figure

ALL = "__all__"
FILTERS = ("year", "quarter", "channel", "category", "subcategory")
Granularity = Literal["month", "quarter"]
MONTHLY_GRANULARITY_OPTIONS = (
    {"label": "Monthly", "value": "month"},
    {"label": "Quarterly", "value": "quarter"},
)
GRANULARITY_SPANS = {"month": "Month", "quarter": "Quarter"}
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
                [
                    dcc.Link(
                        "← Dashboard overview",
                        href="/dashboard",
                        className="button",
                    ),
                    dbc.Button(
                        "Export CSV",
                        id="executive-header-export",
                        n_clicks=0,
                        size="sm",
                        color="secondary",
                        className="button",
                        title="Download the filtered product performance table",
                    ),
                ],
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
            html.P(id="executive-filter-status", role="status", className="muted"),
            html.Div(
                [
                    html.Div(
                        [
                            dcc.Loading(
                                html.Div(placeholder, id=f"executive-kpi-slot-{key}"),
                                id=f"executive-kpi-loading-{key}",
                                type="circle",
                            )
                            for (key, _, _), placeholder in zip(
                                KPI_FIELDS, kpi_cards(note="Loading warehouse data…")
                            )
                        ],
                        id="executive-live-kpis",
                        className="metrics executive-kpis",
                    ),
                    html.Div(
                        [
                            card(
                                html.Span(
                                    "Revenue By Month", id="executive-chart-title"
                                ),
                                [
                                    graph("executive-primary"),
                                    status("executive-primary-status"),
                                ],
                                html.Div(
                                    [
                                        html.Div(
                                            dcc.Dropdown(
                                                id="executive-monthly-granularity",
                                                options=MONTHLY_GRANULARITY_OPTIONS,
                                                value="month",
                                                clearable=False,
                                                persistence=True,
                                                persistence_type="local",
                                                className="chart-granularity",
                                            ),
                                            className="chart-granularity-field",
                                        ),
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
                                                            "Chart type",
                                                            className="muted",
                                                            id="executive-chart-type-label",
                                                        ),
                                                        dcc.RadioItems(
                                                            id="executive-chart-type",
                                                            options=[
                                                                {
                                                                    "label": "Revenue Line",
                                                                    "value": "line",
                                                                },
                                                                {
                                                                    "label": "Revenue + Margin",
                                                                    "value": "dual",
                                                                },
                                                            ],
                                                            value="line",
                                                            persistence=True,
                                                            persistence_type="local",
                                                        ),
                                                    ],
                                                    className="chart-type-options",
                                                    **{
                                                        "aria-labelledby": "executive-chart-type-label"
                                                    },
                                                ),
                                            ],
                                            className="chart-type-menu",
                                        ),
                                    ],
                                    className="heading-extras",
                                ),
                            ),
                            card(
                                html.Span(
                                    "Revenue By Channel",
                                    id="executive-breakdown-title",
                                ),
                                [
                                    graph("executive-secondary"),
                                    status("executive-secondary-status"),
                                ],
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
                                                    "Chart type",
                                                    className="muted",
                                                    id="executive-breakdown-type-label",
                                                ),
                                                dcc.RadioItems(
                                                    id="executive-breakdown-type",
                                                    options=[
                                                        {
                                                            "label": "Revenue By Channel · Bars",
                                                            "value": "bar",
                                                        },
                                                        {
                                                            "label": "Channel Split · Donut",
                                                            "value": "donut",
                                                        },
                                                        {
                                                            "label": "Product Mix · Treemap",
                                                            "value": "treemap",
                                                        },
                                                    ],
                                                    value="bar",
                                                    persistence="channel-views-v2",
                                                    persistence_type="local",
                                                ),
                                            ],
                                            className="chart-type-options",
                                            **{
                                                "aria-labelledby": "executive-breakdown-type-label"
                                            },
                                        ),
                                    ],
                                    className="chart-type-menu",
                                ),
                            ),
                        ],
                        className="report-charts",
                    ),
                    card(
                        "Top categories by revenue",
                        [
                            dcc.Loading(
                                html.Div(ranked_list([]), id="executive-top-products"),
                                type="circle",
                            )
                        ],
                        html.Span(
                            "Top 8 · Share of filtered revenue", className="badge"
                        ),
                    ),
                    product_performance_card(),
                    html.P(id="executive-kpi-status", role="status", className="muted"),
                ],
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


def no_data_figure():
    return {
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


def monthly_figure(values, chart_type="line", granularity: Granularity = "month"):
    """Primary trend chart from the loader's monthly sums.

    Quarterly views sum the mart's monthly rows; margins are recomputed from
    the summed quarters, never averaged.
    """
    points = monthly_points(values["monthly"])
    if not points:
        return no_data_figure()
    trend = pd.DataFrame(
        [
            {
                "Date": datetime(point.year, point.month, 1),
                "revenue": float(point.revenue),
                "profit": float(point.profit),
            }
            for point in points
        ]
    )
    if granularity == "quarter":
        trend = trend.assign(
            Date=pd.PeriodIndex(trend["Date"], freq="Q").to_timestamp()
        )
        trend = (
            trend.groupby("Date", as_index=False)[["revenue", "profit"]]
            .sum()
            .sort_values("Date")
        )
    margin = [
        margin_percentage(revenue, profit)
        for revenue, profit in zip(trend["revenue"], trend["profit"])
    ]
    first = make_subplots(specs=[[{"secondary_y": True}]])
    first.add_trace(
        go.Bar(
            x=trend["Date"],
            y=trend["revenue"],
            name="Gross revenue",
            marker_color=TOKENS["primary"],
            hovertemplate=REVENUE_HOVERTEMPLATE,
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
            hovertemplate=MARGIN_HOVERTEMPLATE,
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
        first.update_traces(hovertemplate=REVENUE_HOVERTEMPLATE)
    first.update_layout(height=340)
    return first


def breakdown_figure(values, breakdown_type="bar"):
    """Secondary channel/category chart from the same loaded rows."""
    if not monthly_points(values["monthly"]):
        return no_data_figure()
    monthly = pd.DataFrame([dict(row) for row in values["monthly"]])
    monthly["revenue"] = monthly["revenue"].astype(float)
    channels = monthly.groupby("sales_channel", as_index=False)["revenue"].sum()
    figure = revenue_breakdown(channels, values["detail"], breakdown_type)
    figure.update_layout(height=340)
    return figure


def report_cards(values):
    """KPI cards; sparklines only when the selection has monthly rows."""
    if not monthly_points(values["monthly"]):
        return kpi_cards(values, "No matching sales · USD")
    return kpi_cards(
        values,
        note=None,
        monthly=values["monthly"],
        monthly_orders=values.get("monthly_orders"),
    )


def detail_rows(values):
    return [
        {
            "Category": row["product_category"],
            "Subcategory": row["product_subcategory"],
            "Revenue (USD)": round(float(row["revenue"]), 2),
            "Gross profit (USD)": round(float(row["profit"]), 2),
            "Units sold": int(row["units"]),
        }
        for row in values["detail"]
    ]


def report_status(values):
    if not monthly_points(values["monthly"]):
        return "No warehouse sales match the selected filters."
    return (
        f"Warehouse artifact · Fetched {values['fetched_at']} · Cached for up to 60 "
        "seconds. Orders count distinct channel/order pairs. AOV is "
        "selected-product revenue per purchasing order."
    )


def top_category_rows(detail, limit=8):
    """Rank category·subcategory pairs by revenue; shares are of positive revenue."""
    frame = pd.DataFrame(detail)
    if frame.empty:
        return []
    frame["revenue"] = frame["revenue"].astype(float)
    grouped = (
        frame.fillna({"product_category": "Unknown", "product_subcategory": "Unknown"})
        .groupby(["product_category", "product_subcategory"], as_index=False)["revenue"]
        .sum()
    )
    grouped = grouped[grouped["revenue"] > 0]
    if grouped.empty:
        return []
    total = float(grouped["revenue"].sum())
    grouped = grouped.sort_values("revenue", ascending=False).head(limit)
    return [
        {
            "name": f"{row.product_category} · {row.product_subcategory}",
            "value": f"${row.revenue:,.2f}",
            "share": row.revenue / total if total > 0 else None,
        }
        for row in grouped.itertuples(index=False)
    ]


@callback(
    *[Output(f"executive-kpi-slot-{key}", "children") for key, _, _ in KPI_FIELDS],
    Output("executive-top-products", "children"),
    Output("executive-detail", "rowData"),
    Output("executive-detail", "columnDefs"),
    Output("executive-detail", "dashGridOptions"),
    Output("executive-kpi-status", "children"),
    Input("executive-filter-catalog", "data"),
    *[Input(f"executive-{name}", "value") for name in FILTERS],
    Input("display-preferences", "data"),
)
def update_report(
    catalog,
    year,
    quarter,
    channel,
    category,
    subcategory,
    preferences,
):
    cards, top_products, rows, columns, settings, status = populate_report(
        catalog,
        year,
        quarter,
        channel,
        category,
        subcategory,
        preferences,
    )
    # Charts have independent callbacks so menu changes do not reload KPIs/table.
    return (*cards, top_products, rows, columns, settings, status)


def populate_chart(
    catalog, filters, chart_type, index, granularity: Granularity = "month"
):
    if catalog is None:
        return feedback({}, "Waiting for warehouse filters.")
    try:
        selected = normalize_filters(catalog, *filters)
        values = load_executive_report(*warehouse_location(), *selected)
        note = ""
        if index == 1:
            figure = monthly_figure(values, chart_type, granularity)
            if values["monthly"]:
                parts = []
                if granularity == "quarter":
                    parts.append("Quarters sum the underlying monthly rows")
                if chart_type == "dual":
                    parts.append(
                        "Gross profit margin = summed profit / summed revenue; zero-revenue periods have no margin."
                    )
                note = "; ".join(parts)
        else:
            figure = breakdown_figure(values, chart_type)
        return feedback(figure, note)
    except dash.exceptions.PreventUpdate:
        raise
    except Exception:
        logging.getLogger(__name__).warning("Executive chart unavailable")
        figure = style_figure(go.Figure())
        figure.add_annotation(
            text="Chart unavailable. Change a filter or reload to retry.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
        return feedback(
            figure, "Chart unavailable. Change a filter or reload to retry."
        )


@callback(
    Output("executive-primary", "figure"),
    Output("executive-primary-status", "children"),
    Input("executive-filter-catalog", "data"),
    *[Input(f"executive-{name}", "value") for name in FILTERS],
    Input("executive-chart-type", "value"),
    Input("executive-monthly-granularity", "value"),
)
def update_monthly_chart(
    catalog, year, quarter, channel, category, subcategory, chart_type, granularity
):
    return populate_chart(
        catalog,
        (year, quarter, channel, category, subcategory),
        chart_type,
        1,
        granularity=granularity,
    )


@callback(
    Output("executive-secondary", "figure"),
    Output("executive-secondary-status", "children"),
    Input("executive-filter-catalog", "data"),
    *[Input(f"executive-{name}", "value") for name in FILTERS],
    Input("executive-breakdown-type", "value"),
)
def update_breakdown_chart(
    catalog, year, quarter, channel, category, subcategory, chart_type
):
    return populate_chart(
        catalog, (year, quarter, channel, category, subcategory), chart_type, 2
    )


def populate_report(
    catalog,
    year,
    quarter,
    channel,
    category,
    subcategory,
    preferences,
):
    columns: list[dict[str, Any]] = [
        {"field": name}
        for name in (
            "Category",
            "Subcategory",
            "Revenue (USD)",
            "Gross profit (USD)",
            "Units sold",
        )
    ]
    for column in columns:
        field = column["field"]
        if field in ("Revenue (USD)", "Gross profit (USD)"):
            precision = 0 if field == "Revenue (USD)" else 2
            column.update(
                type="numericColumn",
                filter="agNumberColumnFilter",
                valueFormatter={
                    "function": f"params.value == null ? '—' : d3.format('$,.{precision}f')(params.value)"
                },
                tooltipValueGetter={
                    "function": "params.value == null ? 'No value' : d3.format('$,.2f')(params.value)"
                },
            )
        if field == "Gross profit (USD)":
            column["cellClassRules"] = {
                "executive-profit-loss": "params.value != null && params.value < 0"
            }
            column["tooltipValueGetter"] = {
                "function": "params.value == null ? 'No value' : (params.value < 0 ? 'Loss: ' : 'Gross profit: ') + d3.format('$,.2f')(params.value)"
            }
    settings = grid_options((preferences or {}).get("pageSize", 10))
    settings["rowClassRules"] = {
        "executive-loss-row": "params.data && params.data['Gross profit (USD)'] != null && params.data['Gross profit (USD)'] < 0"
    }
    if catalog is None:
        return (
            kpi_cards(note="Waiting for warehouse filters"),
            ranked_list([]),
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
        top_products = ranked_list(top_category_rows(values["detail"]))
        return (
            report_cards(values),
            top_products,
            detail_rows(values),
            columns,
            settings,
            report_status(values),
        )
    except dash.exceptions.PreventUpdate:
        raise
    except Exception:
        logging.getLogger(__name__).warning("Executive filtered report unavailable")
        return (
            kpi_cards(note="Warehouse unavailable"),
            ranked_list([]),
            [],
            columns,
            settings,
            "Unable to load this selection. Change a filter or reload to retry.",
        )


@callback(
    Output("executive-chart-title", "children"),
    Input("executive-chart-type", "value"),
    Input("executive-monthly-granularity", "value"),
)
def monthly_chart_title(chart_type, granularity: Granularity = "month"):
    span = GRANULARITY_SPANS.get(granularity, "Month")
    if chart_type == "dual":
        return f"Revenue & Gross Profit Margin by {span}"
    return f"Revenue By {span}"


@callback(
    Output("executive-breakdown-title", "children"),
    Input("executive-breakdown-type", "value"),
)
def breakdown_chart_title(chart_type):
    return {
        "donut": "Omnichannel Sales Split",
        "treemap": "Revenue By Category & Subcategory",
    }.get(chart_type, "Revenue By Channel")


def product_performance_card():
    loading = grid("executive-detail")
    loading.children.defaultColDef["useValueFormatterForExport"] = False
    loading.children.csvExportParams = {
        "fileName": "executive-product-performance.csv",
        "exportedRows": "filteredAndSorted",
    }
    return card("Product performance", [loading])


@callback(
    Output("executive-detail", "exportDataAsCsv"),
    Input("executive-header-export", "n_clicks"),
    prevent_initial_call=True,
)
def export_product_performance(n_clicks):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    return True
