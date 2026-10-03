"""Wholesale account KPI with warehouse filters and remaining sample metrics."""

from decimal import Decimal
import os
import re
import dash_bootstrap_components as dbc

import dash
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html
from dash.exceptions import PreventUpdate
from analytics import REPORTS, report_layout
from theme import TOKENS, style_figure
from components import metric, card, graph, grid
from revenue_kpis import load_filter_catalog, warehouse_location, yoy_badge
from sales_filters import ALL, FIELDS, filter_layout, register_filters, valid_values
from wholesale_kpis import (
    load_wholesale_operations,
    load_top_resellers,
    load_reseller_scatter,
    load_wholesale_product_mix,
    load_active_accounts,
    load_reseller_revenue,
    load_wholesale_orders,
    load_wholesale_comparison,
)

PREFIX = "wholesale-warehouse"

dash.register_page(
    __name__,
    path="/dashboard/wholesale",
    title=REPORTS["wholesale"][0] + " | AdventureWorks",
)


def account_card(value=None, note="Loading warehouse data…"):
    card = metric("Active Resellers", "—" if value is None else f"{value:,}", note)
    if value is not None:
        card.children = card.children[:2]
    card.id = "wholesale-active-accounts"
    card.children.append(
        yoy_badge(
            "value", "currency", {"yoy": {"reason": note or "Select year for YoY"}}
        )
    )
    return compact_card(card, value, currency=False)


def layout():
    page = report_layout("wholesale", sample_filters=False)
    charts = next(
        child
        for child in page.children
        if getattr(child, "className", None) == "report-charts"
    )
    charts.children[1] = secondary_chart_card()
    page.children[-2] = operations_card()
    page.children[1:1] = [
        filter_layout(PREFIX),
        html.P(
            "Warehouse filters apply to all KPIs, charts, and fulfillment records.",
            className="muted",
        ),
        html.Div(
            [
                html.Div(
                    [
                        dcc.Loading(
                            html.Div(account_card(), id="wholesale-account-kpi"),
                            type="circle",
                        ),
                        html.P(
                            id="wholesale-account-status",
                            role="status",
                            className="muted",
                        ),
                    ]
                ),
                html.Div(
                    [
                        dcc.Loading(
                            html.Div(revenue_card(), id="wholesale-revenue-kpi"),
                            type="circle",
                        ),
                        html.P(
                            id="wholesale-revenue-status",
                            role="status",
                            className="muted",
                        ),
                    ]
                ),
                html.Div(
                    [
                        dcc.Loading(
                            html.Div(average_card(), id="wholesale-average-kpi"),
                            type="circle",
                        ),
                        html.P(
                            id="wholesale-average-status",
                            role="status",
                            className="muted",
                        ),
                    ]
                ),
                html.Div(
                    [
                        dcc.Loading(
                            html.Div(units_card(), id="wholesale-units-kpi"),
                            type="circle",
                        ),
                        html.P(
                            id="wholesale-units-status",
                            role="status",
                            className="muted",
                        ),
                    ]
                ),
                html.Div(
                    [
                        dcc.Loading(
                            html.Div(aov_card(), id="wholesale-aov-kpi"), type="circle"
                        ),
                        html.P(
                            id="wholesale-aov-status", role="status", className="muted"
                        ),
                    ]
                ),
            ],
            className="metrics wholesale-warehouse-kpis",
        ),
    ]
    return page


register_filters(PREFIX)


@callback(
    Output("wholesale-account-kpi", "children"),
    Output("wholesale-account-status", "children"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_accounts(catalog, year, quarter, channel, category, subcategory):
    if catalog is None:
        return account_card(note="Waiting for warehouse filters"), ""
    try:
        location = warehouse_location()
        authoritative = load_filter_catalog(*location)
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(authoritative, selections)
        if validated != selections:
            raise PreventUpdate
        count = load_active_accounts(
            *location, *[None if v == ALL else v for v in validated]
        )
        return (
            with_yoy(
                account_card(count, ""),
                "active_accounts",
                count,
                location,
                validated,
                count > 0,
            ),
            ("No wholesale accounts match these filters." if count == 0 else ""),
        )
    except PreventUpdate:
        raise
    except Exception:
        return (
            account_card(note="Warehouse count unavailable"),
            "Unable to load active accounts. Change a filter or reload to retry.",
        )


def revenue_card(value=None, note="Loading warehouse data…"):
    display = "—" if value is None else f"${Decimal(str(value)):,.2f}"
    card = metric("Total Reseller Revenue", display, note)
    if value is not None:
        card.children = card.children[:2]
    card.id = "wholesale-total-reseller-revenue"
    card.children.append(
        yoy_badge(
            "value", "currency", {"yoy": {"reason": note or "Select year for YoY"}}
        )
    )
    return compact_card(card, value, currency=True)


@callback(
    Output("wholesale-revenue-kpi", "children"),
    Output("wholesale-revenue-status", "children"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_revenue(catalog, year, quarter, channel, category, subcategory):
    if catalog is None:
        return revenue_card(note="Waiting for warehouse filters"), ""
    try:
        location = warehouse_location()
        authoritative = load_filter_catalog(*location)
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(authoritative, selections)
        if validated != selections:
            raise PreventUpdate
        result = load_reseller_revenue(
            *location, *[None if v == ALL else v for v in validated]
        )
        return (
            with_yoy(
                revenue_card(result["total_reseller_revenue"], ""),
                "total_reseller_revenue",
                result["total_reseller_revenue"],
                location,
                validated,
                result["source_rows"],
            ),
            (
                "No reseller sales match these filters."
                if not result["source_rows"]
                else ""
            ),
        )
    except PreventUpdate:
        raise
    except Exception:
        return (
            revenue_card(note="Warehouse revenue unavailable"),
            "Unable to load reseller revenue. Change a filter or reload to retry.",
        )


def average_card(value=None, note="Loading warehouse data…"):
    display = "—" if value is None else f"${value:,.2f}"
    card = metric("Revenue per Reseller", display, note)
    if value is not None:
        card.children = card.children[:2]
    card.id = "wholesale-average-revenue-per-reseller"
    card.children.append(
        yoy_badge(
            "value", "currency", {"yoy": {"reason": note or "Select year for YoY"}}
        )
    )
    return compact_card(card, value, currency=True)


@callback(
    Output("wholesale-average-kpi", "children"),
    Output("wholesale-average-status", "children"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_average(catalog, year, quarter, channel, category, subcategory):
    if catalog is None:
        return average_card(note="Waiting for warehouse filters"), ""
    try:
        location = warehouse_location()
        authoritative = load_filter_catalog(*location)
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(authoritative, selections)
        if validated != selections:
            raise PreventUpdate
        parameters = [None if v == ALL else v for v in validated]
        # Reuse the same cached, unrounded totals and filters as KPIs 1 and 2.
        accounts = load_active_accounts(*location, *parameters)
        revenue = load_reseller_revenue(*location, *parameters)
        if not accounts:
            return (
                average_card(note="No active reseller accounts"),
                "Average is undefined when the active account count is zero.",
            )
        if not revenue["source_rows"]:
            return (
                average_card(note="No reseller revenue data"),
                "No reseller sales match these filters.",
            )
        average = Decimal(str(revenue["total_reseller_revenue"])) / Decimal(accounts)
        return (
            with_yoy(
                average_card(average, ""),
                "revenue_per_reseller",
                average,
                location,
                validated,
                True,
            ),
            "",
        )
    except PreventUpdate:
        raise
    except Exception:
        return (
            average_card(note="Warehouse average unavailable"),
            "Unable to load average revenue per reseller. Change a filter or reload to retry.",
        )


def units_card(value=None, note="Loading warehouse data…"):
    card = metric(
        "Total Wholesale Units Sold", "—" if value is None else f"{int(value):,}", note
    )
    if value is not None:
        card.children = card.children[:2]
    card.id = "wholesale-total-units-sold"
    card.children.append(
        yoy_badge(
            "value", "currency", {"yoy": {"reason": note or "Select year for YoY"}}
        )
    )
    return compact_card(card, value, currency=False)


@callback(
    Output("wholesale-units-kpi", "children"),
    Output("wholesale-units-status", "children"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_units(catalog, year, quarter, channel, category, subcategory):
    if catalog is None:
        return units_card(note="Waiting for warehouse filters"), ""
    try:
        location = warehouse_location()
        authoritative = load_filter_catalog(*location)
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(authoritative, selections)
        if validated != selections:
            raise PreventUpdate
        # Revenue and units share one cached warehouse aggregation and filter scope.
        result = load_reseller_revenue(
            *location, *[None if v == ALL else v for v in validated]
        )
        return (
            with_yoy(
                units_card(result["total_wholesale_units_sold"], ""),
                "total_wholesale_units_sold",
                result["total_wholesale_units_sold"],
                location,
                validated,
                result["source_rows"],
            ),
            (
                "No reseller sales match these filters."
                if not result["source_rows"]
                else ""
            ),
        )
    except PreventUpdate:
        raise
    except Exception:
        return (
            units_card(note="Warehouse units unavailable"),
            "Unable to load wholesale units. Change a filter or reload to retry.",
        )


def aov_card(value=None, note="Loading warehouse data…"):
    card = metric("Wholesale AOV", "—" if value is None else f"${value:,.2f}", note)
    if value is not None:
        card.children = card.children[:2]
    card.id = "wholesale-average-order-value"
    card.children.append(
        yoy_badge(
            "value", "currency", {"yoy": {"reason": note or "Select year for YoY"}}
        )
    )
    return compact_card(card, value, currency=True)


@callback(
    Output("wholesale-aov-kpi", "children"),
    Output("wholesale-aov-status", "children"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_aov(catalog, year, quarter, channel, category, subcategory):
    if catalog is None:
        return aov_card(note="Waiting for warehouse filters"), ""
    try:
        location = warehouse_location()
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(load_filter_catalog(*location), selections)
        if validated != selections:
            raise PreventUpdate
        parameters = [None if v == ALL else v for v in validated]
        orders = load_wholesale_orders(*location, *parameters)
        revenue = load_reseller_revenue(*location, *parameters)
        if not orders:
            return (
                aov_card(note="No wholesale orders"),
                "AOV is undefined when the order count is zero.",
            )
        if not revenue["source_rows"]:
            return (
                aov_card(note="No reseller revenue data"),
                "No reseller sales match these filters.",
            )
        value = Decimal(str(revenue["total_reseller_revenue"])) / Decimal(orders)
        return (
            with_yoy(
                aov_card(value, ""), "wholesale_aov", value, location, validated, True
            ),
            "",
        )
    except PreventUpdate:
        raise
    except Exception:
        return (
            aov_card(note="Warehouse AOV unavailable"),
            "Unable to load wholesale AOV. Change a filter or reload to retry.",
        )


def with_yoy(card, key, current, location, selections, has_current):
    year, quarter, channel, category, subcategory = [
        None if v == ALL else v for v in selections
    ]
    comparison = {"reason": "Select year for YoY"}
    if year is not None:
        period = f"{year} {quarter or 'full year'} vs {year - 1} {quarter or 'full year'} · Same channel and product filters; available calendar-period totals"
        try:
            previous = load_wholesale_comparison(
                *location, year - 1, quarter, channel, category, subcategory
            )
            comparison = {"period": period, "previous": previous}
            if not previous.get("source_rows"):
                comparison["reason"] = "No prior-year data"
            elif not has_current:
                comparison["reason"] = "No current-period data"
            elif previous.get(key) is None:
                comparison["reason"] = "Prior-year metric unavailable"
        except Exception:
            comparison = {"period": period, "reason": "YoY unavailable"}
    card.children[-1] = yoy_badge(
        key,
        (
            "currency"
            if key not in ("active_accounts", "total_wholesale_units_sold")
            else "count"
        ),
        {key: current, "yoy": comparison},
    )
    return card


def compact_card(card, value, currency=False):
    """Display compact values while preserving exact totals for hover inspection."""
    if value is None:
        return card
    number = Decimal(str(value))
    prefix = "$" if currency else ""
    exact = f"${number:,.2f}" if currency else f"{int(number):,}"
    display = exact
    for threshold, suffix in ((10**12, "T"), (10**9, "B"), (10**6, "M"), (10**3, "K")):
        if abs(number) >= threshold:
            compact = f"{number / threshold:.2f}".rstrip("0").rstrip(".")
            display = f"{prefix}{compact}{suffix}"
            break
    card.children[1].children = display
    card.children[1].title = exact
    return card


def leaderboard_figure(rows=None, message="No reseller sales match these filters."):
    if not rows:
        figure = style_figure(go.Figure())
        figure.add_annotation(
            text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False
        )
        figure.update_xaxes(visible=False)
        figure.update_yaxes(visible=False)
    else:
        frame = pd.DataFrame(rows)
        frame["exact_revenue"] = frame["revenue"].map(
            lambda value: f"${Decimal(str(value)):,.2f}"
        )
        frame["revenue"] = frame["revenue"].astype(float)
        figure = style_figure(
            px.bar(
                frame,
                x="revenue",
                y="reseller_name",
                orientation="h",
                custom_data=["exact_revenue"],
                labels={"revenue": "Revenue (USD)", "reseller_name": "Reseller"},
                color_discrete_sequence=[TOKENS["primary"]],
            )
        )
        figure.update_traces(
            hovertemplate="%{y}<br>Revenue: %{customdata[0]}<extra></extra>"
        )
        figure.update_yaxes(
            categoryorder="array",
            categoryarray=list(frame["reseller_name"])[::-1],
            automargin=True,
        )
        figure.update_xaxes(tickprefix="$", tickformat="~s")
    figure.update_layout(height=420, showlegend=False)
    return figure


@callback(
    Output("wholesale-primary", "figure"),
    Output("wholesale-leaderboard-status", "children"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_leaderboard(catalog, year, quarter, channel, category, subcategory):
    if catalog is None:
        return leaderboard_figure(message="Waiting for warehouse filters"), ""
    try:
        location = warehouse_location()
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(load_filter_catalog(*location), selections)
        if validated != selections:
            raise PreventUpdate
        rows = load_top_resellers(
            *location, *[None if v == ALL else v for v in validated]
        )
        return (
            leaderboard_figure(rows),
            "Warehouse data · Top 10 by reseller revenue · USD",
        )
    except PreventUpdate:
        raise
    except Exception:
        return (
            leaderboard_figure(message="Leaderboard unavailable"),
            "Unable to load top resellers. Change a filter or reload to retry.",
        )


def secondary_chart_card():
    return card(
        html.Span("Wholesale product mix", id="wholesale-secondary-title"),
        [
            graph("wholesale-secondary"),
            html.P(id="wholesale-secondary-status", role="status", className="muted"),
        ],
        html.Details(
            [
                html.Summary(
                    "•••",
                    title="Choose wholesale chart",
                    **{"aria-label": "Choose wholesale chart"},
                ),
                html.Div(
                    [
                        html.Span("Chart type", className="muted"),
                        dcc.RadioItems(
                            id="wholesale-secondary-type",
                            options=[
                                {"label": "Product mix · Bars", "value": "bar"},
                                {
                                    "label": "B2B Client Value Segmentation · Scatter",
                                    "value": "scatter",
                                },
                            ],
                            value="bar",
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


def reseller_scatter_figure(rows):
    if not rows:
        return leaderboard_figure(
            message="No reseller sales with recorded annual revenue match these filters."
        )
    frame = pd.DataFrame(rows)
    frame["revenue_label"] = frame["annual_revenue"].map(
        lambda value: f"${Decimal(str(value)):,.2f}"
    )
    frame["units_label"] = frame["total_units_sold"].map(
        lambda value: f"{int(value):,}"
    )
    frame["annual_revenue"] = frame["annual_revenue"].astype(float)
    frame["total_units_sold"] = frame["total_units_sold"].astype(float)
    figure = style_figure(
        px.scatter(
            frame,
            x="annual_revenue",
            y="total_units_sold",
            hover_name="reseller_name",
            custom_data=["reseller_name", "revenue_label", "units_label"],
            labels={
                "annual_revenue": "Reseller annual revenue (USD)",
                "total_units_sold": "Units sold",
            },
            color_discrete_sequence=[TOKENS["teal"]],
        )
    )
    figure.update_traces(
        marker={"size": 10, "opacity": 0.6},
        hovertemplate="%{customdata[0]}<br>Annual revenue: %{customdata[1]}<br>Units sold: %{customdata[2]}<extra></extra>",
    )
    figure.update_xaxes(
        title_text="Reseller annual revenue (USD)", tickprefix="$", tickformat="~s"
    )
    figure.update_yaxes(title_text="Units sold", tickformat="~s", rangemode="tozero")
    figure.update_layout(height=420, showlegend=False)
    return figure


@callback(
    Output("wholesale-secondary", "figure"),
    Output("wholesale-secondary-title", "children"),
    Output("wholesale-secondary-status", "children"),
    Input("wholesale-secondary-type", "value"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_secondary(
    chart_type, catalog, year, quarter, channel, category, subcategory
):
    title = (
        "B2B Client Value Segmentation"
        if chart_type == "scatter"
        else "Wholesale product mix"
    )
    if catalog is None:
        return leaderboard_figure(message="Waiting for warehouse filters"), title, ""
    try:
        location = warehouse_location()
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(load_filter_catalog(*location), selections)
        if validated != selections:
            raise PreventUpdate
        if chart_type != "scatter":
            rows = load_wholesale_product_mix(
                *location, *[None if v == ALL else v for v in validated]
            )
            if len(rows) > 1000:
                return (
                    leaderboard_figure(
                        message="Too many categories. Narrow the filters."
                    ),
                    title,
                    "Limit: 1,000 categories.",
                )
            return (
                product_mix_figure(rows),
                title,
                "Warehouse data · Reseller revenue by product category · USD",
            )
        rows = load_reseller_scatter(
            *location, *[None if v == ALL else v for v in validated]
        )
        if len(rows) > 1000:
            return (
                leaderboard_figure(
                    message="Too many resellers to display. Narrow the filters."
                ),
                title,
                "Limit: 1,000 resellers.",
            )
        return (
            reseller_scatter_figure(rows),
            title,
            "Warehouse data · One point per reseller with recorded annual revenue. Annual revenue is a company attribute; units sold follow the selected filters.",
        )
    except PreventUpdate:
        raise
    except Exception:
        return (
            leaderboard_figure(message="Chart unavailable"),
            title,
            "Unable to load wholesale chart data. Change a filter or reload to retry.",
        )


def product_mix_figure(rows):
    if not rows:
        return leaderboard_figure(message="No reseller sales match these filters.")
    frame = pd.DataFrame(rows)
    frame["exact_revenue"] = frame["revenue"].map(
        lambda value: f"${Decimal(str(value)):,.2f}"
    )
    frame["revenue"] = frame["revenue"].astype(float)
    figure = style_figure(
        px.bar(
            frame,
            x="product_category",
            y="revenue",
            color="product_category",
            custom_data=["exact_revenue"],
            labels={"product_category": "Category", "revenue": "Revenue (USD)"},
            color_discrete_sequence=[
                TOKENS["primary"],
                TOKENS["teal"],
                "#8862AB",
                "#BD7529",
            ],
        )
    )
    figure.update_traces(
        hovertemplate="%{x}<br>Revenue: %{customdata[0]}<extra></extra>"
    )
    figure.update_yaxes(tickprefix="$", tickformat="~s")
    figure.update_layout(height=420)
    return figure


def operations_columns():
    number = {
        "function": "params.value == null ? '—' : d3.format(',.2f')(params.value)"
    }
    return [
        {"field": "reseller_name", "headerName": "Reseller Name", "minWidth": 190},
        {
            "field": "order_frequency",
            "headerName": "Order Frequency Code",
            "minWidth": 155,
        },
        {
            "field": "total_orders_count",
            "headerName": "Total Orders Count",
            "type": "numericColumn",
            "filter": "agNumberColumnFilter",
            "minWidth": 130,
        },
        {
            "field": "average_units_per_order",
            "headerName": "Average Units per Order",
            "type": "numericColumn",
            "filter": "agNumberColumnFilter",
            "valueFormatter": number,
            "minWidth": 155,
        },
        {
            "field": "average_shipping_lead_days",
            "headerName": "Average Shipping Lead Time (Days)",
            "type": "numericColumn",
            "filter": "agNumberColumnFilter",
            "minWidth": 205,
            "valueFormatter": {
                "function": "params.value == null ? '—' : d3.format(',.2f')(params.value) + (params.value > 5 ? ' · Over target' : '')"
            },
            "cellClassRules": {
                "wholesale-lead-alert": "params.value != null && params.value > 5"
            },
        },
        {
            "field": "territory",
            "headerName": "Territory Region / Country",
            "minWidth": 200,
        },
    ]


def operations_card():
    loading = grid("wholesale-detail")
    loading.children.columnDefs = operations_columns()
    loading.children.defaultColDef.update(
        wrapHeaderText=True, autoHeaderHeight=True, useValueFormatterForExport=False
    )
    loading.children.csvExportParams = {
        "fileName": "wholesale-operations-fulfillment.csv",
        "exportedRows": "filteredAndSorted",
    }
    return card(
        "Wholesale Operations & Fulfillment Matrix",
        [
            html.P(
                "Shipping target: 5 calendar days. Over-target cells are marked in red. Geography reflects the buyer’s state/province and country.",
                className="muted",
            ),
            loading,
        ],
        dbc.Button(
            "Export CSV",
            id="wholesale-detail-export",
            n_clicks=0,
            size="sm",
            color="secondary",
            className="button",
        ),
    )


@callback(
    Output("wholesale-detail", "rowData"),
    Output("wholesale-status", "children"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_operations(catalog, year, quarter, channel, category, subcategory):
    if catalog is None:
        return [], "Waiting for warehouse filters"
    try:
        location = warehouse_location()
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(load_filter_catalog(*location), selections)
        if validated != selections:
            raise PreventUpdate
        staging = os.environ.get("BQ_STAGING_DATASET", "silver_adventureworks")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", staging):
            raise ValueError("Invalid staging dataset")
        rows = load_wholesale_operations(
            *location, staging, *[None if v == ALL else v for v in validated]
        )
        if len(rows) > 1000:
            return [], "More than 1,000 accounts match. Narrow the warehouse filters."
        labels = {"M": "Monthly", "Q": "Quarterly", "S": "Semiannually", "A": "Monthly"}
        records = []
        for row in rows:
            record = dict(row)
            frequency = str(record.get("order_frequency") or "").strip()
            record["order_frequency"] = labels.get(
                frequency.upper(), frequency or "Unknown"
            )
            record["territory"] = (
                " / ".join(
                    str(record.get(k) or "").strip()
                    for k in ("state_province_name", "country_region_name")
                    if record.get(k)
                )
                or "Unknown"
            )
            for key in ("average_units_per_order", "average_shipping_lead_days"):
                record[key] = (
                    float(record[key]) if record.get(key) is not None else None
                )
            records.append(record)
        return records, ("" if records else "No reseller invoices match these filters.")
    except PreventUpdate:
        raise
    except Exception:
        return (
            [],
            "Unable to load fulfillment records. Change a filter or reload to retry.",
        )


@callback(
    Output("wholesale-detail", "exportDataAsCsv"),
    Input("wholesale-detail-export", "n_clicks"),
    prevent_initial_call=True,
)
def export_wholesale_operations(n_clicks):
    if not n_clicks:
        raise PreventUpdate
    return True
