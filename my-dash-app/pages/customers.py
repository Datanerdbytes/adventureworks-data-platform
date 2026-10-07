"""Warehouse customer KPIs, demographic charts, and regional ledger."""

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html, ctx, no_update
from dash.exceptions import PreventUpdate

from analytics import REPORTS, report_layout
from components import metric, card, graph, field, grid
from customer_kpis import (
    load_customer_scorecards,
    load_customer_demographics,
    load_customer_map,
    load_customer_lifecycle,
    load_customer_segment_revenue,
    load_customer_ledger,
)
from customer_map import OVERVIEW, revenue_map
import plotly.express as px
import plotly.graph_objects as go
from theme import TOKENS, style_figure
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
    page = report_layout("customers", sample_filters=False)
    # Replace the shared report placeholders with warehouse-backed components.
    page.children[2].hidden = True
    page.children[3].children[0] = region_chart_card()
    page.children[3].children[1] = lifecycle_chart_card()
    page.children[-2] = customer_ledger_card()
    page.children[1:1] = [
        filter_layout(PREFIX),
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
    ]
    page.children.insert(
        -2, html.P(id="customers-chart-status", className="muted", role="status")
    )
    return page


register_filters(PREFIX)


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
            f"As of {data['as_of']} · Acquired retail profiles"
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


AGE_GROUPS = ["Under 18", "18–29", "30–44", "45–59", "60+", "Unknown"]


def demographic_figures(rows, empty_message="No retail customers match these filters."):
    if not rows:

        def empty():
            figure = style_figure(go.Figure())
            figure.add_annotation(
                text=empty_message,
                x=0.5,
                y=0.5,
                xref="paper",
                yref="paper",
                showarrow=False,
            )
            return figure

        return empty(), empty()
    regions, ages = {}, {}
    for row in rows:
        regions[row["region"]] = regions.get(row["region"], 0) + int(row["customers"])
        ages[row["age_group"]] = ages.get(row["age_group"], 0) + int(row["customers"])
    ordered = sorted(regions, key=lambda name: (regions[name], name))
    region = style_figure(
        px.bar(
            x=[regions[name] for name in ordered],
            y=ordered,
            orientation="h",
            labels={"x": "Customers", "y": "Region / Country"},
            color_discrete_sequence=[TOKENS["primary"]],
        )
    )
    region.update_traces(hovertemplate="%{y}<br>Customers: %{x:,.0f}<extra></extra>")
    region.update_xaxes(tickformat=",d")
    age = style_figure(
        px.bar(
            x=[a for a in AGE_GROUPS if a in ages],
            y=[ages[a] for a in AGE_GROUPS if a in ages],
            labels={"x": "Age group", "y": "Customers"},
            color_discrete_sequence=[TOKENS["teal"]],
        )
    )
    age.update_traces(hovertemplate="%{x}<br>Customers: %{y:,.0f}<extra></extra>")
    age.update_xaxes(categoryorder="array", categoryarray=AGE_GROUPS)
    age.update_yaxes(tickformat=",d")
    return region, age


def populate_demographics(catalog, year, quarter, channel, category, subcategory):
    if catalog is None:
        return (
            demographic_figures([], "Waiting for warehouse filters")[1],
            "Waiting for warehouse filters.",
        )
    try:
        location = warehouse_location()
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(load_filter_catalog(*location), selections)
        if validated != selections:
            raise PreventUpdate
        normalized = [None if v == ALL else v for v in validated]
        rows = load_customer_demographics(*location, *normalized)
        note = (
            f"Purchasing retail customers · Age as of {rows[0]['as_of']}"
            if rows
            else "No retail customers match these filters. Reseller accounts do not have retail customer demographics."
        )
        return demographic_figures(rows)[1], note
    except PreventUpdate:
        raise
    except Exception:
        return (
            demographic_figures([], "Chart data unavailable")[1],
            "Unable to load warehouse demographics. Change a filter or reload to retry.",
        )


def region_chart_card():
    plot = graph("customers-primary")
    plot.children.responsive = True
    plot.parent_className = "customer-chart-loading"
    plot.children.config["topojsonURL"] = "/assets/geo/"
    return card(
        html.Span("Retail Customers By Region", id="customers-primary-title"),
        [
            html.Div(
                [
                    field(
                        "Sales territory group",
                        dcc.Dropdown(
                            id="customers-map-group",
                            options=[
                                {"label": "All territory groups", "value": OVERVIEW}
                            ],
                            value=OVERVIEW,
                            clearable=False,
                        ),
                    ),
                ],
                id="customers-map-controls",
                hidden=True,
            ),
            html.Div(plot, className="customer-chart-frame"),
            html.P(id="customers-map-status", role="status", className="muted"),
        ],
        html.Details(
            [
                html.Summary(
                    "•••",
                    title="Choose regional chart",
                    **{"aria-label": "Choose regional chart"},
                ),
                html.Div(
                    [
                        html.Span("Chart type", className="muted"),
                        dcc.RadioItems(
                            id="customers-primary-type",
                            options=[
                                {
                                    "label": "Retail Customers By Region · Bars",
                                    "value": "bar",
                                },
                                {"label": "Geographic Map · Revenue", "value": "map"},
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


@callback(
    Output("customers-map-group", "value"),
    Input("customers-primary", "clickData"),
    Input("customers-primary-type", "value"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
    State("customers-map-group", "value"),
    prevent_initial_call=True,
)
def navigate_map(
    click, chart_type, year, quarter, channel, category, subcategory, group
):
    if ctx.triggered_id != "customers-primary":
        return OVERVIEW
    if chart_type == "map" and group == OVERVIEW and click:
        custom = (click.get("points") or [{}])[0].get("customdata", [])
        if len(custom) > 2 and isinstance(custom[2], str):
            return custom[2]
    return no_update


@callback(
    Output("customers-primary", "figure"),
    Output("customers-primary-title", "children"),
    Output("customers-map-controls", "hidden"),
    Output("customers-map-group", "options"),
    Output("customers-map-status", "children"),
    Input("customers-primary-type", "value"),
    Input("customers-map-group", "value"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_region(
    chart_type, group, catalog, year, quarter, channel, category, subcategory
):
    is_map = chart_type == "map"
    title = "Geographic Map" if is_map else "Retail Customers By Region"
    options = [dict(label="All territory groups", value=OVERVIEW)]
    message = "Waiting for warehouse filters"
    if catalog is not None:
        try:
            location = warehouse_location()
            selections = [year, quarter, channel, category, subcategory]
            _, validated = valid_values(load_filter_catalog(*location), selections)
            if validated != selections:
                raise PreventUpdate
            normalized = [None if v == ALL else v for v in validated]
            if is_map:
                rows = load_customer_map(*location, *normalized)
                groups = sorted({r["territory_group"] or "Unknown" for r in rows})
                options += [dict(label=g, value=g) for g in groups]
                selected = group if group in groups else OVERVIEW
                figure, note = revenue_map(rows, selected)
                return (
                    figure,
                    title,
                    False,
                    options,
                    note + " Boundaries: Natural Earth (public domain).",
                )
            rows = load_customer_demographics(*location, *normalized)
            return demographic_figures(rows)[0], title, True, options, ""
        except PreventUpdate:
            raise
        except Exception:
            message = (
                "Unable to load regional data. Change a filter or reload to retry."
            )
    return demographic_figures([], message)[0], title, not is_map, options, message


LIFECYCLE_STAGES = ["New Cohort", "Active Repeat", "Slipping Account", "Dormant"]


def lifecycle_figure(
    rows, empty_message="No retail customer profiles match these filters"
):
    counts = {r["stage"]: int(r["customers"]) for r in rows}
    if not sum(counts.values()):
        return demographic_figures([], empty_message)[1]
    figure = px.funnel(
        x=[counts.get(stage, 0) for stage in LIFECYCLE_STAGES],
        y=LIFECYCLE_STAGES,
        orientation="h",
        labels={"x": "Distinct customers", "y": "Lifecycle stage"},
    )
    figure.update_traces(
        marker_color=TOKENS["primary"],
        textinfo="value",
        texttemplate="%{value:,.0f}",
        customdata=[
            "At most one recorded order; active within 90 days",
            "Repeat buyer; active within 90 days",
            "91–180 days since last order",
            "Over 180 days since last order",
        ],
        hovertemplate="%{y}<br>%{x:,.0f} customers<br>%{customdata}<br>Missing order history uses first purchase.<extra></extra>",
    )
    figure = style_figure(figure)
    figure.update_yaxes(
        categoryorder="array",
        categoryarray=LIFECYCLE_STAGES,
        autorange="reversed",
        title=None,
    )
    figure.update_layout(margin=dict(l=125, r=20, t=20, b=40), showlegend=False)
    return figure


def lifecycle_chart_card():
    plot = graph("customers-secondary")
    plot.children.responsive = True
    plot.parent_className = "customer-chart-loading"
    return card(
        html.Span("Retail Customer Age Distribution", id="customers-secondary-title"),
        [html.Div(plot, className="customer-chart-frame")],
        html.Details(
            [
                html.Summary(
                    "•••",
                    title="Choose customer chart",
                    **{"aria-label": "Choose customer chart"},
                ),
                html.Div(
                    [
                        html.Span("Chart type", className="muted"),
                        dcc.RadioItems(
                            id="customers-secondary-type",
                            options=[
                                {
                                    "label": "Retail Customer Age Distribution · Bars",
                                    "value": "age",
                                },
                                *[
                                    dict(label=title, value=key)
                                    for key, title in SEGMENT_TITLES.items()
                                ],
                                {
                                    "label": "Customer Lifecycle Funnel Chart",
                                    "value": "funnel",
                                },
                            ],
                            value="age",
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


@callback(
    Output("customers-secondary", "figure"),
    Output("customers-chart-status", "children"),
    Output("customers-secondary-title", "children"),
    Input("customers-secondary-type", "value"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_customer_chart(
    chart_type, catalog, year, quarter, channel, category, subcategory
):
    if chart_type in SEGMENT_TITLES:
        return populate_segment_revenue(
            chart_type, catalog, year, quarter, channel, category, subcategory
        )
    if chart_type != "funnel":
        figure, note = populate_demographics(
            catalog, year, quarter, channel, category, subcategory
        )
        return figure, note, "Retail Customer Age Distribution"
    title = "Customer Lifecycle Funnel Chart"
    if catalog is None:
        return (
            lifecycle_figure([], "Waiting for warehouse filters"),
            "Waiting for warehouse filters.",
            title,
        )
    try:
        location = warehouse_location()
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(load_filter_catalog(*location), selections)
        if validated != selections:
            raise PreventUpdate
        normalized = [None if v == ALL else v for v in validated]
        rows = load_customer_lifecycle(*location, *normalized)
        note = (
            f"As of {rows[0]['as_of']} · Lifecycle snapshot, not cohort conversion"
            if rows
            else "No retail customer profiles match these filters. Reseller accounts are excluded from the customer lifecycle."
        )
        return lifecycle_figure(rows), note, title
    except PreventUpdate:
        raise
    except Exception:
        return (
            lifecycle_figure([], "Chart data unavailable"),
            "Unable to load warehouse lifecycle data. Change a filter or reload to retry.",
            title,
        )


SEGMENT_TITLES = {
    "income": "Revenue By Income Tier",
    "occupation": "Revenue By Occupation Type",
    "education": "Revenue By Education Level",
}
INCOME_TIERS = [
    "Low Income (<30k)",
    "Middle Income (30k-70k)",
    "High Income (70k-100k)",
    "Very High Income (100k+)",
    "Unknown",
]


def segment_revenue_figure(
    rows, dimension, empty_message="No retail revenue matches these filters"
):
    if not rows:
        return demographic_figures([], empty_message)[1]
    ordered = (
        sorted(
            rows,
            key=lambda r: (
                INCOME_TIERS.index(r["segment"])
                if r["segment"] in INCOME_TIERS
                else len(INCOME_TIERS)
            ),
        )
        if dimension == "income"
        else sorted(rows, key=lambda r: (-float(r["revenue"] or 0), r["segment"]))
    )
    figure = px.bar(
        x=[float(r["revenue"] or 0) for r in ordered],
        y=[r["segment"] for r in ordered],
        orientation="h",
        color_discrete_sequence=[TOKENS["teal"]],
    )
    figure = style_figure(figure)
    figure.update_traces(hovertemplate="%{y}<br>Revenue: $%{x:,.2f}<extra></extra>")
    figure.update_yaxes(
        title=None,
        categoryorder="array",
        categoryarray=[r["segment"] for r in ordered],
        autorange="reversed",
        automargin=True,
    )
    figure.update_xaxes(title="Revenue (USD)", tickprefix="$", tickformat="~s")
    figure.update_layout(hovermode="closest", margin=dict(l=10, r=20, t=20, b=50))
    return figure


def populate_segment_revenue(
    dimension, catalog, year, quarter, channel, category, subcategory
):
    title = SEGMENT_TITLES[dimension]
    if catalog is None:
        return (
            segment_revenue_figure([], dimension, "Waiting for warehouse filters"),
            "Waiting for warehouse filters.",
            title,
        )
    try:
        location = warehouse_location()
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(load_filter_catalog(*location), selections)
        if validated != selections:
            raise PreventUpdate
        normalized = [None if v == ALL else v for v in validated]
        rows = load_customer_segment_revenue(*location, dimension, *normalized)
        note = (
            "Selected-period retail revenue · USD"
            if rows
            else "No retail revenue matches these filters. Reseller accounts do not have retail customer demographics."
        )
        return segment_revenue_figure(rows, dimension), note, title
    except PreventUpdate:
        raise
    except Exception:
        return (
            segment_revenue_figure([], dimension, "Chart data unavailable"),
            "Unable to load warehouse demographic revenue. Change a filter or reload to retry.",
            title,
        )


def customer_ledger_columns():
    definitions = [
        ("state", "State / Province", None),
        ("territory", "Territory Group", None),
        ("customers", "Total Customers", ",.0f"),
        ("revenue", "Total Revenue Generated", "$,.2f"),
        ("dominant_income", "Dominant Income Tier", None),
        ("top_occupation", "Top Occupation Type", None),
        ("average_orders", "Avg Order Frequency", ",.2f"),
        ("dormant", "Dormant Profile Count", ",.0f"),
    ]
    columns = []
    for key, label, fmt in definitions:
        col = dict(field=key, headerName=label, minWidth=160)
        if fmt:
            col.update(
                type="numericColumn",
                filter="agNumberColumnFilter",
                valueFormatter={"function": f"d3.format('{fmt}')(params.value)"},
            )
        columns.append(col)
    columns[0].update(minWidth=220, tooltipField="country")
    return columns


def customer_ledger_card():
    table = grid("customers-detail")
    table.children.columnDefs = customer_ledger_columns()
    table.children.defaultColDef.update(
        wrapHeaderText=True, autoHeaderHeight=True, useValueFormatterForExport=False
    )
    table.children.csvExportParams = dict(
        fileName="customer-demographic-regional-ledger.csv",
        exportedRows="filteredAndSorted",
    )
    return card(
        "Granular Customer Demographic & Regional Ledger",
        [
            html.P(
                "Acquired retail profiles · Cumulative sales through the reporting cutoff",
                className="muted",
            ),
            table,
        ],
        dbc.Button(
            "Export CSV",
            id="customers-ledger-export",
            n_clicks=0,
            size="sm",
            color="secondary",
            className="button",
        ),
    )


@callback(
    Output("customers-detail", "exportDataAsCsv"),
    Input("customers-ledger-export", "n_clicks"),
    prevent_initial_call=True,
)
def export_customer_ledger(clicks):
    if not clicks:
        raise PreventUpdate
    return True


@callback(
    Output("customers-detail", "rowData"),
    Output("customers-status", "children"),
    Input(f"{PREFIX}-catalog", "data"),
    *[Input(f"{PREFIX}-{name}", "value") for name in FIELDS],
)
def populate_customer_ledger(catalog, year, quarter, channel, category, subcategory):
    if catalog is None:
        return [], "Waiting for warehouse filters."
    try:
        location = warehouse_location()
        selections = [year, quarter, channel, category, subcategory]
        _, validated = valid_values(load_filter_catalog(*location), selections)
        if validated != selections:
            raise PreventUpdate
        rows = load_customer_ledger(
            *location, *[None if v == ALL else v for v in validated]
        )
        records = []
        for row in rows:
            record = dict(row)
            record["state"] = f"{row['state']} / {row['country']}"
            for key in ("revenue", "average_orders"):
                record[key] = float(row[key] or 0)
            record.pop("as_of", None)
            records.append(record)
        note = (
            f"{len(records):,} states/provinces · As of {rows[0]['as_of']} · Dormant: >180 days inactive"
            if records
            else "No acquired retail profiles match these filters. Reseller accounts are excluded."
        )
        return records, note
    except PreventUpdate:
        raise
    except Exception:
        return (
            [],
            "Unable to load the warehouse customer ledger. Change a filter or reload to retry.",
        )
