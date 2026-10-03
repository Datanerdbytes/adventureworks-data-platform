"""Customer and regional KPI report with explicitly separated sample visuals."""

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html
from dash.exceptions import PreventUpdate

from analytics import REPORTS, report_layout, register_report_callbacks
from components import metric
from customer_kpis import load_customer_scorecards
from revenue_kpis import load_filter_catalog, warehouse_location
from sales_filters import ALL, FIELDS, filter_layout, register_filters, valid_values

PREFIX = "customers-warehouse"
LABELS = (
    "Total Customer Base",
    "Avg Customer Value",
    "Top Revenue Territory",
    "Top Growth State",
    "Customer Churn Rate",
)

dash.register_page(
    __name__,
    path="/dashboard/customers",
    title=REPORTS["customers"][0] + " | AdventureWorks",
)


def kpi_card(
    label, value="—", badge="Waiting for filters", note="Waiting for warehouse filters"
):
    result = metric(label, value, None)
    result.children[1].title = value
    result.children[2] = dbc.Badge(
        badge,
        color=None,
        className="kpi-yoy kpi-yoy--neutral",
        title=note,
    )
    return result


def layout():
    page = report_layout("customers")
    # Preserve sample callbacks and controls, but replace their visible KPI strip.
    page.children[2].hidden = True
    page.children[1:1] = [
        filter_layout(PREFIX),
        html.P(
            "Warehouse filters apply to these five KPIs. Customer metrics describe retail profiles; reseller sales contribute only to the territory ranking.",
            className="muted",
        ),
        html.Div(
            [
                dcc.Loading(
                    html.Div(kpi_card(label), id=f"{PREFIX}-kpi-{i}"), type="circle"
                )
                for i, label in enumerate(LABELS)
            ],
            className="metrics executive-kpis customer-kpis",
        ),
        html.P(id=f"{PREFIX}-status", className="muted", role="status"),
        html.H2("Sample charts and detail", className="warehouse-kpi-heading"),
        html.P(
            "The sample year and region below control synthetic charts and detail only.",
            className="muted",
        ),
    ]
    return page


register_filters(PREFIX)
register_report_callbacks("customers")


def render_scorecards(data, channel=None):
    from decimal import Decimal
    from pages.growth import compact

    if data.get("as_of") is None:
        return [
            kpi_card(
                label,
                badge="No reporting data",
                note="No warehouse dates match this period.",
            )
            for label in LABELS
        ]
    count = int(data.get("customers") or 0)
    cutoff = str(data.get("as_of") or "unavailable")
    retail = channel != "Reseller"
    cards = []
    cards.append(
        kpi_card(
            LABELS[0],
            compact(count) if retail else "—",
            "Acquired profiles" if retail else "Not applicable",
            "Distinct retail profiles acquired by the reporting cutoff, including dormant customers. Product filters select profiles that have ever bought those products by the cutoff.",
        )
    )
    if retail and count:
        average = Decimal(str(data["customer_revenue"])) / count
        value_card = kpi_card(
            LABELS[1],
            compact(average, currency=True),
            "Revenue / customer",
            "Cumulative retail revenue through the cutoff / acquired profiles, retaining product filters.",
        )
        value_card.children[1].title = f"${average:,.2f}"
    else:
        value_card = kpi_card(
            LABELS[1],
            badge="No customers" if retail else "Not applicable",
            note=(
                "No customer profiles match this scope."
                if retail
                else "Reseller sales have no retail customer keys."
            ),
        )
    cards.append(value_card)
    territory = data.get("top_territory")
    cards.append(
        kpi_card(
            LABELS[2],
            territory["territory"] if territory else "—",
            "Highest revenue" if territory else "No matching sales",
            (
                f"Selected-period revenue: ${territory['revenue']:,.2f}"
                if territory
                else "No matching sales"
            ),
        )
    )
    state = data.get("top_state")
    baseline_available = data.get("state_baseline_available", False)
    cards.append(
        kpi_card(
            LABELS[3],
            state["state"] if state and retail else "—",
            (
                f"+{state['increase']:,} orders"
                if state and retail
                else (
                    ("No growth" if baseline_available else "Baseline unavailable")
                    if retail
                    else "Not applicable"
                )
            ),
            (
                f"{state['country']} · {state['current_orders']:,} vs {state['previous_orders']:,} distinct invoices; latest reporting month vs previous calendar month. Partial months use available totals."
                if state and retail
                else (
                    (
                        "No positive order increase in the latest reporting month."
                        if baseline_available
                        else "No retail sales history in the preceding calendar month."
                    )
                    if retail
                    else "Reseller sales have no retail customer states."
                )
            ),
        )
    )
    cards.append(
        kpi_card(
            LABELS[4],
            f"{100 * data['dormant'] / count:.2f}%" if retail and count else "—",
            (
                "Dormant >180 days"
                if retail and count
                else "No customers" if retail else "Not applicable"
            ),
            f"Acquired profiles with no retail order in any category for over 180 days as of {cutoff}.",
        )
    )
    if retail:
        cards[0].children[1].title = f"{count:,}"
    return cards


@callback(
    *[Output(f"{PREFIX}-kpi-{i}", "children") for i in range(5)],
    Output(f"{PREFIX}-status", "children"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_scorecards(catalog, year, quarter, channel, category, subcategory):
    if catalog is None:
        return *[kpi_card(label) for label in LABELS], "Waiting for warehouse filters."
    try:
        location = warehouse_location()
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(load_filter_catalog(*location), selections)
        if validated != selections:
            raise PreventUpdate
        normalized = [None if v == ALL else v for v in validated]
        data = load_customer_scorecards(*location, *normalized)
        status = (
            f"As of {data['as_of']} (capped at the latest warehouse date). Customer base includes all acquired profiles, including dormant customers. Value is cumulative revenue per profile through the cutoff; product filters select historical purchasers of those products. Churn checks their last retail order across all products. State growth ranks absolute invoice increases in the latest reporting month versus the preceding month."
            if data.get("as_of")
            else "No sales match the selected filters."
        )
        return *render_scorecards(data, normalized[2]), status
    except PreventUpdate:
        raise
    except Exception:
        return (
            *[
                kpi_card(
                    label,
                    badge="Data unavailable",
                    note="Reload or change filters to retry.",
                )
                for label in LABELS
            ],
            "Unable to load customer KPIs. Reload or change filters to retry.",
        )
