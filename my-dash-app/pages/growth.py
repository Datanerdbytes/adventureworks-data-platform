"""Warehouse-backed time-series report with shared sales filters."""

from decimal import Decimal
import calendar

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html
from dash.exceptions import PreventUpdate
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from analytics import REPORTS
from components import card, graph, grid, heading, metric
from data import grid_options
from revenue_kpis import load_executive_report, load_filter_catalog, warehouse_location
from sales_filters import ALL, FIELDS, filter_layout, register_filters, valid_values
from theme import TOKENS, style_figure
from growth_kpis import (
    load_growth_scorecards,
    calculate_scorecards,
    load_day_type_sales,
    load_seasonality_matrix,
    load_growth_ledger,
)

PREFIX = "growth-warehouse"
KPI_LABELS = (
    "QoQ Growth %",
    "YoY Growth %",
    "Rolling 30-Day Run Rate",
    "Peak Seasonality Multiplier",
    "Avg Daily Order Velocity",
)

dash.register_page(
    __name__, path="/dashboard/growth", title=REPORTS["growth"][0] + " | AdventureWorks"
)


def layout():
    return html.Div(
        [
            heading(
                REPORTS["growth"][0],
                "Track monthly sales momentum and calendar seasonality.",
                dcc.Link("← Dashboard overview", href="/dashboard", className="button"),
            ),
            filter_layout(PREFIX),
            html.P(
                "Filters apply to all five KPIs, both charts, and the table. Comparisons use historical baselines outside the selected period. QoQ uses the latest selected quarter; YoY uses the latest selected year (same quarter when selected). Run rate is trailing 30-day revenue ending on the latest selected sales date. Partial periods use available sales.",
                className="muted",
            ),
            html.Div(
                [
                    dcc.Loading(
                        html.Div(
                            growth_card(
                                label, "—", "Loading…", "Loading warehouse data"
                            ),
                            id=f"growth-kpi-{i}",
                        ),
                        type="circle",
                    )
                    for i, label in enumerate(KPI_LABELS)
                ],
                className="metrics executive-kpis growth-kpis",
            ),
            html.Div(
                [
                    primary_chart_card(),
                    secondary_chart_card(),
                ],
                className="report-charts",
            ),
            ledger_card(),
            html.P(id="growth-status", role="status", className="muted"),
        ],
        className="analytics-report",
    )


register_filters(PREFIX)


def ledger_card():
    table = grid("growth-detail")
    table.children.defaultColDef.update(wrapHeaderText=True, autoHeaderHeight=True)
    table.children.dashGridOptions = {**grid_options(), "paginationPageSize": 12}
    table.children.csvExportParams = {
        "fileName": "growth-seasonality-pacing-ledger.csv",
        "exportedRows": "filteredAndSorted",
    }
    return card(
        "Granular Seasonality & Pacing Ledger",
        [
            html.P(
                "Revenue and weekday/weekend sales volumes are USD amounts. Export includes the rows matching the grid filters, in their current sort order.",
                className="muted",
            ),
            table,
        ],
        dbc.Button(
            "Export CSV",
            id="growth-ledger-export",
            className="button",
            n_clicks=0,
            size="sm",
            color="secondary",
        ),
    )


def detail_columns():
    definitions = [
        ("period", "Time Period", None),
        ("revenue", "Total Gross Revenue", "$,.2f"),
        ("orders", "Order Volume Baseline", ",.0f"),
        ("weekday_revenue", "Weekday Sales Volume", "$,.2f"),
        ("weekend_revenue", "Weekend Sales Volume", "$,.2f"),
        ("weekend_share", "Weekend Vol % Split", ".2f"),
        ("mom_growth", "MoM Growth %", "+.2f"),
    ]
    columns = []
    for field, title, fmt in definitions:
        column = {
            "field": field,
            "headerName": title,
            "minWidth": 145,
            "useValueFormatterForExport": False,
        }
        if field == "period":
            column.update(
                minWidth=175,
                sort="asc",
                valueFormatter={
                    "function": "params.value == null ? '' : params.value.slice(0,4) + ' - ' + ['January','February','March','April','May','June','July','August','September','October','November','December'][Number(params.value.slice(5,7))-1]"
                },
            )
        else:
            suffix = " + '%'" if field in ("weekend_share", "mom_growth") else ""
            column.update(
                type="numericColumn",
                filter="agNumberColumnFilter",
                valueFormatter={
                    "function": f"params.value == null ? '—' : d3.format('{fmt}')(params.value){suffix}"
                },
            )
        columns.append(column)
    return columns


@callback(
    Output("growth-detail", "exportDataAsCsv"),
    Input("growth-ledger-export", "n_clicks"),
    prevent_initial_call=True,
)
def export_growth_ledger(n_clicks):
    if not n_clicks:
        raise PreventUpdate
    return True


def empty_figure(message):
    figure = style_figure(go.Figure())
    figure.add_annotation(
        text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False
    )
    return figure


def compact(value, currency=False):
    amount = Decimal(str(value))
    prefix = "$" if currency else ""
    for divisor, suffix in ((10**12, "T"), (10**9, "B"), (10**6, "M"), (10**3, "K")):
        if abs(amount) >= divisor:
            return f"{prefix}{amount / divisor:,.2f}{suffix}"
    return f"{prefix}{amount:,.2f}" if currency else f"{amount:,.0f}"


def monthly_totals(rows):
    totals = {}
    for row in rows:
        month = list(calendar.month_name).index(row["month_name"].strip())
        period = pd.Period(year=int(row["calendar_year"]), month=month, freq="M")
        totals[period] = totals.get(period, Decimal(0)) + Decimal(str(row["revenue"]))
    return totals


def render_growth(values, baseline):
    selected = monthly_totals(values["monthly"])
    history = monthly_totals(baseline["monthly"])
    if not selected:
        return (
            empty_figure("No matching sales"),
            empty_figure("No matching sales"),
            [],
            "No warehouse sales match these filters.",
        )
    rows = []
    for period, revenue in sorted(selected.items()):
        prior = history.get(period - 1)
        growth = (
            float((revenue / prior - 1) * 100)
            if prior is not None and prior > 0
            else None
        )
        rows.append(
            {
                "Month": str(period),
                "Revenue (USD)": float(revenue),
                "Monthly growth (%)": growth,
            }
        )
    available = [
        row["Monthly growth (%)"]
        for row in rows
        if row["Monthly growth (%)"] is not None
    ]
    frame = pd.DataFrame(rows)
    frame["Year"] = frame["Month"].str[:4]
    frame["Calendar month"] = frame["Month"].str[5:].astype(int)
    first = style_figure(
        px.line(
            frame,
            x="Calendar month",
            y="Revenue (USD)",
            color="Year",
            markers=True,
            custom_data=["Month"],
            color_discrete_sequence=[
                TOKENS["primary"],
                TOKENS["teal"],
                "#8862AB",
                "#BD7529",
            ],
        )
    )
    first.update_xaxes(
        tickmode="array",
        tickvals=list(range(1, 13)),
        ticktext=list(calendar.month_abbr)[1:],
    )
    first.update_yaxes(tickprefix="$", tickformat="~s")
    first.update_traces(
        hovertemplate="%{customdata[0]}<br>Revenue: $%{y:,.2f}<extra></extra>"
    )
    second = style_figure(
        px.bar(
            frame,
            x="Month",
            y="Monthly growth (%)",
            color_discrete_sequence=[TOKENS["teal"]],
        )
    )
    second.update_traces(
        hovertemplate="%{x}<br>Monthly growth: %{y:+.2f}%<extra></extra>"
    )
    second.update_yaxes(ticksuffix="%")
    if not available:
        second = empty_figure("No positive preceding-month baseline available")
    return (
        first,
        second,
        rows,
        "Warehouse data · Missing months and zero/negative baselines have no growth rate. Partial months use available sales.",
    )


@callback(
    Output("growth-detail", "rowData"),
    Output("growth-detail", "columnDefs"),
    Output("growth-detail", "dashGridOptions"),
    Output("growth-status", "children"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
    Input("display-preferences", "data"),
)
def populate_growth(
    catalog, year, quarter, channel, category, subcategory, preferences
):
    columns = detail_columns()
    settings = {**grid_options(), "paginationPageSize": 12}
    message = "Waiting for warehouse filters"
    if catalog is not None:
        try:
            location = warehouse_location()
            selections = [year, quarter, channel, category, subcategory]
            _, validated = valid_values(load_filter_catalog(*location), selections)
            if validated != selections:
                raise PreventUpdate
            normalized = [None if value == ALL else value for value in validated]
            data = load_growth_ledger(*location, *normalized)
            rows = []
            for item in data:
                row = {
                    "period": pd.Timestamp(item["month"]).strftime("%Y-%m"),
                    "orders": int(item["orders"]),
                }
                for key in (
                    "revenue",
                    "weekday_revenue",
                    "weekend_revenue",
                    "weekend_share",
                    "mom_growth",
                ):
                    row[key] = float(item[key]) if item.get(key) is not None else None
                rows.append(row)
            status = "MoM compares the preceding calendar month with the same product/channel filters. Missing months and nonpositive baselines show —. CSV exports numeric values and sortable YYYY-MM periods."
            return (
                rows,
                columns,
                settings,
                status if rows else "No warehouse sales match these filters.",
            )
        except PreventUpdate:
            raise
        except Exception:
            message = "Unable to load growth data. Change a filter or reload to retry."
    return [], columns, settings, message


def growth_card(label, display, badge_label, explanation, tone="neutral"):
    result = metric(label, display, None)
    result.id = f"growth-scorecard-{KPI_LABELS.index(label)}"
    result.children[1].title = display
    result.children[2] = dbc.Badge(
        badge_label,
        color=None,
        className=f"kpi-yoy kpi-yoy--{tone}",
        title=explanation,
    )
    return result


def scorecard_cards(values):
    cards = []
    for label, key in zip(KPI_LABELS, ("qoq", "yoy", "rolling", "peak", "velocity")):
        value = values[key]
        if value is None:
            display = "—"
        elif key in ("qoq", "yoy"):
            display = f"{value:+.2f}%"
        elif key == "rolling":
            display = compact(value, currency=True)
        elif key == "peak":
            display = f"{value:.2f}×"
        else:
            display = f"{value:,.2f}"
        note = values[f"{key}_note"]
        tone = "neutral"
        badge_label = {
            "qoq": "QoQ",
            "yoy": "YoY",
            "rolling": "30-day revenue",
            "peak": "Seasonality",
            "velocity": "Orders/day",
        }[key]
        if value is None:
            badge_label = (
                "No matching sales" if note == "No matching sales" else "Unavailable"
            )
        elif key in ("qoq", "yoy"):
            tone = "positive" if value > 0 else "negative" if value < 0 else "neutral"
            direction = "↑" if value > 0 else "↓" if value < 0 else "→"
            badge_label = f"{direction} {badge_label}"
        result = growth_card(label, display, badge_label, note, tone)
        if value is not None and key == "rolling":
            result.children[1].title = f"${value:,.2f}"
        cards.append(result)
    return cards


@callback(
    *[Output(f"growth-kpi-{i}", "children") for i in range(5)],
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_scorecards(catalog, year, quarter, channel, category, subcategory):
    message = "Waiting for warehouse filters"
    if catalog is not None:
        try:
            location = warehouse_location()
            selections = [year, quarter, channel, category, subcategory]
            _, validated = valid_values(load_filter_catalog(*location), selections)
            if validated != selections:
                raise PreventUpdate
            normalized = [None if v == ALL else v for v in validated]
            data = load_growth_scorecards(*location, *normalized)
            cards = scorecard_cards(calculate_scorecards(data, *normalized[:2]))
            return cards
        except PreventUpdate:
            raise
        except Exception:
            message = "Scorecard data unavailable · reload to retry"
    badge_label = "Waiting for filters" if catalog is None else "Data unavailable"
    return [growth_card(label, "—", badge_label, message) for label in KPI_LABELS]


def primary_chart_card():
    return card(
        html.Span("Monthly revenue comparison", id="growth-primary-title"),
        [
            graph("growth-primary"),
            html.P(id="growth-primary-status", role="status", className="muted"),
        ],
        html.Details(
            [
                html.Summary(
                    "•••",
                    title="Choose revenue chart",
                    **{"aria-label": "Choose revenue chart"},
                ),
                html.Div(
                    [
                        html.Span("Chart type", className="muted"),
                        dcc.RadioItems(
                            id="growth-primary-type",
                            options=[
                                {
                                    "label": "Monthly revenue comparison · Line",
                                    "value": "line",
                                },
                                {
                                    "label": "Weekend vs. Weekday Sales Volume · Bars",
                                    "value": "day-type",
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
    )


def day_type_figure(rows):
    if not rows:
        return empty_figure("No sales match these filters")
    values = {}
    for row in rows:
        period = pd.Period(
            year=int(row["calendar_year"]), month=int(row["month_number"]), freq="M"
        )
        values[(period, bool(row["is_weekend_flag"]))] = Decimal(str(row["revenue"]))
    periods = sorted({period for period, _ in values})
    data = []
    for period in periods:
        for weekend in (False, True):
            revenue = values.get((period, weekend), Decimal(0))
            data.append(
                {
                    "Month": period.strftime("%b %Y"),
                    "Day type": "Weekend" if weekend else "Weekday",
                    "Revenue (USD)": float(revenue),
                    "Exact revenue": f"${revenue:,.2f}",
                }
            )
    figure = style_figure(
        px.bar(
            pd.DataFrame(data),
            x="Month",
            y="Revenue (USD)",
            color="Day type",
            barmode="group",
            custom_data=["Exact revenue", "Day type"],
            category_orders={
                "Month": [p.strftime("%b %Y") for p in periods],
                "Day type": ["Weekday", "Weekend"],
            },
            color_discrete_map={
                "Weekday": TOKENS["primary"],
                "Weekend": TOKENS["teal"],
            },
        )
    )
    figure.update_traces(
        hovertemplate="%{x}<br>%{customdata[1]}: %{customdata[0]}<extra></extra>"
    )
    figure.update_yaxes(
        title_text="Total sales amount (USD)", tickprefix="$", tickformat="~s"
    )
    figure.update_layout(barmode="group", hovermode="closest")
    return figure


@callback(
    Output("growth-primary", "figure"),
    Output("growth-primary-title", "children"),
    Output("growth-primary-status", "children"),
    Input("growth-primary-type", "value"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_primary(
    chart_type, catalog, year, quarter, channel, category, subcategory
):
    title = (
        "Weekend vs. Weekday Sales Volume"
        if chart_type == "day-type"
        else "Monthly revenue comparison"
    )
    if catalog is None:
        return empty_figure("Waiting for warehouse filters"), title, ""
    try:
        location = warehouse_location()
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(load_filter_catalog(*location), selections)
        if validated != selections:
            raise PreventUpdate
        normalized = [None if v == ALL else v for v in validated]
        if chart_type == "day-type":
            rows = load_day_type_sales(*location, *normalized)
            return (
                day_type_figure(rows),
                title,
                "Total sales amount by order-date weekday/weekend; totals are not normalized by number of days. Use Sales channel to compare Internet and Reseller behavior.",
            )
        values = load_executive_report(*location, *normalized)
        first, _, _, _ = render_growth(values, values)
        return first, title, ""
    except PreventUpdate:
        raise
    except Exception:
        return (
            empty_figure("Chart unavailable"),
            title,
            "Unable to load revenue chart data. Change a filter or reload to retry.",
        )


def secondary_chart_card():
    return card(
        html.Span("Month-over-month revenue growth", id="growth-secondary-title"),
        [
            graph("growth-secondary"),
            html.P(id="growth-secondary-status", role="status", className="muted"),
        ],
        html.Details(
            [
                html.Summary(
                    "•••",
                    title="Choose growth chart",
                    **{"aria-label": "Choose growth chart"},
                ),
                html.Div(
                    [
                        html.Span("Chart type", className="muted"),
                        dcc.RadioItems(
                            id="growth-secondary-type",
                            options=[
                                {
                                    "label": "Month-over-month revenue growth · Bars",
                                    "value": "growth",
                                },
                                {
                                    "label": "Annual Seasonality Peak Matrix · Heatmap",
                                    "value": "matrix",
                                },
                            ],
                            value="growth",
                            persistence=True,
                            persistence_type="local",
                        ),
                    ],
                    className="chart-type-options",
                ),
            ],
            className="chart-type-menu",
        ),
    )


def seasonality_matrix_figure(rows):
    if not rows:
        return empty_figure("No sales match these filters")
    days = list(calendar.day_name)
    months = list(calendar.month_name)[1:]
    values = {
        (int(row["month_number"]), row["day_name"].strip()): int(row["units"])
        for row in rows
    }
    active_months = {month for month, _ in values}
    z = [
        [
            values.get((month, day), 0) if month in active_months else None
            for month in range(1, 13)
        ]
        for day in days
    ]
    figure = style_figure(
        go.Figure(
            go.Heatmap(
                x=months,
                y=days,
                z=z,
                colorscale=[[0, TOKENS["background"]], [1, TOKENS["teal"]]],
                colorbar={"title": "Units sold", "thickness": 12},
                xgap=2,
                ygap=2,
                hoverongaps=False,
                hovertemplate="%{y} · %{x}<br>Units sold: %{z:,.0f}<extra></extra>",
            )
        )
    )
    figure.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=months,
        tickmode="array",
        tickvals=months,
        ticktext=list(calendar.month_abbr)[1:],
        tickangle=-45,
        tickfont={"size": 10},
        showgrid=False,
    )
    figure.update_yaxes(
        type="category",
        categoryorder="array",
        categoryarray=days,
        autorange="reversed",
        showgrid=False,
    )
    figure.update_layout(
        hovermode="closest", margin={"l": 85, "r": 35, "t": 25, "b": 65}
    )
    return figure


@callback(
    Output("growth-secondary", "figure"),
    Output("growth-secondary-title", "children"),
    Output("growth-secondary-status", "children"),
    Input("growth-secondary-type", "value"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_secondary(
    chart_type, catalog, year, quarter, channel, category, subcategory
):
    title = (
        "Annual Seasonality Peak Matrix"
        if chart_type == "matrix"
        else "Month-over-month revenue growth"
    )
    if catalog is None:
        return empty_figure("Waiting for warehouse filters"), title, ""
    try:
        location = warehouse_location()
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(load_filter_catalog(*location), selections)
        if validated != selections:
            raise PreventUpdate
        normalized = [None if v == ALL else v for v in validated]
        if chart_type == "matrix":
            rows = load_seasonality_matrix(*location, *normalized)
            scope = (
                "All available years combined"
                if normalized[0] is None
                else str(normalized[0])
            )
            return (
                seasonality_matrix_figure(rows),
                title,
                f"{scope} · Total units sold, not a daily average. Blank months have no matching data.",
            )
        values = load_executive_report(*location, *normalized)
        baseline = (
            values
            if normalized[:2] == [None, None]
            else load_executive_report(*location, None, None, *normalized[2:])
        )
        _, second, _, _ = render_growth(values, baseline)
        return second, title, ""
    except PreventUpdate:
        raise
    except Exception:
        return (
            empty_figure("Chart unavailable"),
            title,
            "Unable to load growth chart data. Change a filter or reload to retry.",
        )
