"""Wholesale account KPI with warehouse filters and remaining sample metrics."""

from decimal import Decimal

import dash
from dash import Input, Output, callback, dcc, html
from dash.exceptions import PreventUpdate
from analytics import REPORTS, report_layout, register_report_callbacks
from components import metric
from revenue_kpis import load_filter_catalog, warehouse_location, yoy_badge
from sales_filters import ALL, FIELDS, filter_layout, register_filters, valid_values
from wholesale_kpis import (
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
    page.children[1:1] = [
        filter_layout(PREFIX),
        html.P(
            "Warehouse filters apply to all five KPIs. "
            "The charts and detail table remain synthetic examples "
            "for 2026 across all regions.",
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
register_report_callbacks("wholesale", sample_filters=False)


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
