"""Shared layouts and deterministic, offline business analytics fixtures."""

import logging

import pandas as pd
import plotly.express as px
from dash import Input, Output, callback, dcc, html

from components import card, field, graph, grid, heading, metric
from data import grid_options
from theme import TOKENS, style_figure
from revenue_kpis import kpi_cards

REPORTS = {
    "executive": (
        "Executive Revenue & Sales Performance",
        "Revenue & Sales",
        "Revenue, order value, and channel contribution at a glance.",
    ),
    "wholesale": (
        "B2B Wholesale & Reseller Analytics",
        "Wholesale & Resellers",
        "Understand reseller contribution, order volume, and product mix.",
    ),
    "growth": (
        "Time-Series Growth & Seasonal Dynamics",
        "Growth & Seasonality",
        "Track monthly momentum and patterns across the sample calendar.",
    ),
    "customers": (
        "Customer Demographics & Regional Footprint",
        "Customers & Regions",
        "Explore the age distribution and regional footprint of retail buyers.",
    ),
}
REGIONS = (
    "United States",
    "Canada",
    "United Kingdom",
    "Germany",
    "France",
    "Australia",
)
COLORS = [TOKENS["primary"], TOKENS["teal"], "#8862AB", "#BD7529"]


def sales_fixture():
    """One synthetic order per active account/month; identifiers stay consistent."""
    rows = []
    for year in (2025, 2026):
        for month in range(1, 13):
            for customer in range(1, 241):
                if (customer + month) % 4 == 0:
                    continue
                wholesale = customer % 5 < 2
                units = 12 + (customer + month) % 39 if wholesale else 1 + customer % 4
                price = (340, 75, 48)[customer % 3]
                revenue = round(
                    units
                    * price
                    * (1 + 0.025 * (year - 2025))
                    * (1.18 if month in (6, 7, 11, 12) else 1),
                    2,
                )
                rows.append(
                    {
                        "Date": pd.Timestamp(year, month, 1),
                        "Year": year,
                        "Month": month,
                        "Customer": f"C-{customer:04}",
                        "Age group": ("18–29", "30–44", "45–59", "60+")[
                            (customer // 6) % 4
                        ],
                        "Region": REGIONS[customer % 6],
                        "Channel": "Reseller" if wholesale else "Internet",
                        "Reseller": (
                            f"Partner {customer % 18 + 1:02}" if wholesale else None
                        ),
                        "Category": ("Bikes", "Accessories", "Clothing")[customer % 3],
                        "Units": units,
                        "Revenue": revenue,
                        "Gross profit": round(
                            revenue * (0.24 if wholesale else 0.36), 2
                        ),
                    }
                )
    return pd.DataFrame(rows)


def report_layout(kind):
    title, _, description = REPORTS[kind]
    return html.Div(
        [
            heading(
                title,
                description,
                dcc.Link("← Dashboard overview", href="/dashboard", className="button"),
            ),
            *(
                [
                    html.H2("Warehouse KPIs", className="warehouse-kpi-heading"),
                    dcc.Store(id="executive-kpi-load", data=True),
                    dcc.Loading(
                        html.Div(
                            kpi_cards(note="Loading warehouse totals…"),
                            id="executive-live-kpis",
                            className="metrics executive-kpis",
                        ),
                        type="circle",
                    ),
                    html.P(id="executive-kpi-status", role="status", className="muted"),
                    html.H2(
                        "Sample charts and detail", className="warehouse-kpi-heading"
                    ),
                    html.P(
                        "The filters below apply only to the synthetic charts and detail table. Warehouse KPIs above cover all available years and regions.",
                        className="muted",
                    ),
                ]
                if kind == "executive"
                else []
            ),
            html.Div(
                [
                    field(
                        "Sample year",
                        dcc.Dropdown(
                            [2025, 2026],
                            2026,
                            id=f"{kind}-year",
                            clearable=False,
                            persistence=True,
                            persistence_type="session",
                        ),
                    ),
                    field(
                        "Region",
                        dcc.Dropdown(
                            ["All regions", *REGIONS],
                            "All regions",
                            id=f"{kind}-region",
                            clearable=False,
                            persistence=True,
                            persistence_type="session",
                        ),
                    ),
                ],
                className="filters",
            ),
            html.Div(
                id=f"{kind}-metrics", className="metrics", hidden=kind == "executive"
            ),
            html.Div(
                [
                    card(
                        {
                            "executive": "Revenue by month",
                            "wholesale": "Revenue by reseller",
                            "growth": "Monthly revenue comparison",
                            "customers": "Retail customers by region",
                        }[kind],
                        [graph(f"{kind}-primary")],
                    ),
                    card(
                        {
                            "executive": "Revenue by channel",
                            "wholesale": "Wholesale product mix",
                            "growth": "Month-over-month revenue growth",
                            "customers": "Retail customer age distribution",
                        }[kind],
                        [graph(f"{kind}-secondary")],
                    ),
                ],
                className="report-charts",
            ),
            card(
                "Supporting detail",
                [grid(f"{kind}-detail")],
                html.Span("Synthetic data · USD", className="badge"),
            ),
            html.P(id=f"{kind}-status", role="status", className="muted"),
        ],
        className="analytics-report",
    )


def build_report(kind, year, region, preferences=None):
    """Aggregate first; only summaries reach graphs and the grid."""
    if year not in (2025, 2026) or region not in ("All regions", *REGIONS):
        return empty_report("No sample data matches these filters.", preferences)
    all_sales = sales_fixture()
    if region != "All regions":
        all_sales = all_sales[all_sales["Region"] == region]
    selected = all_sales[all_sales["Year"] == year]
    if kind == "wholesale":
        selected = selected[selected["Channel"] == "Reseller"]
    elif kind == "customers":
        selected = selected[selected["Channel"] == "Internet"]
    if selected.empty:
        return empty_report("No sample data matches these filters.", preferences)
    revenue = selected["Revenue"].sum()
    metrics = [
        metric("Revenue", f"${revenue:,.0f}", "USD · selected sample period"),
        metric("Orders", f"{len(selected):,}", "One row per synthetic order"),
        metric(
            "Average order value",
            f"${revenue / len(selected):,.0f}",
            "Revenue divided by orders",
        ),
        metric(
            "Gross margin",
            f"{selected['Gross profit'].sum() / revenue:.1%}",
            "Gross profit divided by revenue",
        ),
    ]
    monthly = selected.groupby("Date", as_index=False)[
        ["Revenue", "Gross profit", "Units"]
    ].sum()
    monthly["Orders"] = selected.groupby("Date").size().values
    first = px.line(
        monthly, x="Date", y="Revenue", markers=True, color_discrete_sequence=COLORS
    )
    note = "All figures are deterministic synthetic examples, not production results. Currency: USD."
    if kind == "executive":
        channel = selected.groupby("Channel", as_index=False)["Revenue"].sum()
        second = px.bar(
            channel,
            x="Channel",
            y="Revenue",
            color="Channel",
            color_discrete_sequence=COLORS,
        )
        detail = monthly.rename(columns={"Date": "Month"})
        detail["Month"] = detail["Month"].dt.strftime("%Y-%m")
    elif kind == "wholesale":
        detail = selected.groupby(["Reseller", "Region"], as_index=False).agg(
            Revenue=("Revenue", "sum"),
            Orders=("Revenue", "size"),
            Units=("Units", "sum"),
        )
        ranked = detail.sort_values("Revenue", ascending=True)
        first = px.bar(
            ranked,
            y="Reseller",
            x="Revenue",
            orientation="h",
            color_discrete_sequence=COLORS,
        )
        category = selected.groupby("Category", as_index=False)["Revenue"].sum()
        second = px.bar(
            category,
            x="Category",
            y="Revenue",
            color="Category",
            color_discrete_sequence=COLORS,
        )
        metrics[3] = metric(
            "Active resellers",
            str(selected["Reseller"].nunique()),
            "Distinct partners in selection",
        )
        note += " Wholesale reports include only the reseller channel."
    elif kind == "growth":
        comparisons = all_sales.groupby(["Year", "Month"], as_index=False)[
            "Revenue"
        ].sum()
        comparisons["Year"] = comparisons["Year"].astype(str)
        first = px.line(
            comparisons,
            x="Month",
            y="Revenue",
            color="Year",
            markers=True,
            color_discrete_sequence=COLORS,
        )
        first.update_xaxes(dtick=1)
        timeline = (
            all_sales.groupby("Date", as_index=False)["Revenue"]
            .sum()
            .sort_values("Date")
        )
        timeline["Growth (%)"] = timeline["Revenue"].pct_change() * 100
        detail = timeline[timeline["Date"].dt.year == year].copy()
        second = px.bar(
            detail, x="Date", y="Growth (%)", color_discrete_sequence=COLORS
        )
        available = detail["Growth (%)"].dropna()
        metrics[2] = metric(
            "Average monthly growth",
            f"{available.mean():+.1f}%" if len(available) else "—",
            "Arithmetic mean of available months",
        )
        metrics[3] = metric(
            "Peak revenue month",
            str(selected.groupby("Month")["Revenue"].sum().idxmax()),
            "Calendar month number",
        )
        detail["Date"] = detail["Date"].dt.strftime("%Y-%m")
        note += " Comparison shows both sample years; growth and detail use the selected year. January 2025 has no prior-month baseline. Seasonal variation is simulated."
    else:
        customers = selected.drop_duplicates("Customer")
        region_counts = (
            customers.groupby("Region", as_index=False)
            .size()
            .rename(columns={"size": "Customers"})
        )
        first = px.bar(
            region_counts,
            x="Customers",
            y="Region",
            orientation="h",
            color_discrete_sequence=COLORS,
        )
        age_counts = (
            customers.groupby("Age group", as_index=False)
            .size()
            .rename(columns={"size": "Customers"})
        )
        second = px.bar(
            age_counts,
            x="Age group",
            y="Customers",
            color_discrete_sequence=[TOKENS["teal"]],
        )
        detail = selected.groupby(["Region", "Age group"], as_index=False).agg(
            Customers=("Customer", "nunique"),
            Orders=("Revenue", "size"),
            Revenue=("Revenue", "sum"),
        )
        metrics = [
            metric(
                "Retail customers", str(len(customers)), "Distinct purchasing accounts"
            ),
            metric(
                "Regions served",
                str(customers["Region"].nunique()),
                "Regions with retail purchases",
            ),
            metric(
                "Revenue per customer",
                f"${revenue / len(customers):,.0f}",
                "Retail revenue / distinct customers",
            ),
            metric(
                "Orders per customer",
                f"{len(selected) / len(customers):.1f}",
                "Retail orders / distinct customers",
            ),
        ]
        note += " Demographics cover distinct Internet-channel customers; wholesale accounts are excluded."
    records = (
        detail.round(2).astype(object).where(pd.notna(detail), None).to_dict("records")
    )
    figures = [style_figure(fig) for fig in (first, second)]
    for fig in figures:
        fig.update_layout(height=340)
    return (
        metrics,
        *figures,
        records,
        [{"field": column} for column in detail.columns],
        grid_options((preferences or {}).get("pageSize", 10)),
        note,
    )


def empty_report(message, preferences):
    figure = {
        "data": [],
        "layout": {
            "template": "plotly_white",
            "annotations": [
                {
                    "text": message,
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
        [],
        figure,
        figure,
        [],
        [],
        grid_options((preferences or {}).get("pageSize", 10)),
        message,
    )


def register_report_callbacks(kind):
    @callback(
        Output(f"{kind}-metrics", "children"),
        Output(f"{kind}-primary", "figure"),
        Output(f"{kind}-secondary", "figure"),
        Output(f"{kind}-detail", "rowData"),
        Output(f"{kind}-detail", "columnDefs"),
        Output(f"{kind}-detail", "dashGridOptions"),
        Output(f"{kind}-status", "children"),
        Input(f"{kind}-year", "value"),
        Input(f"{kind}-region", "value"),
        Input("display-preferences", "data"),
    )
    def populate(year, region, preferences):
        try:
            return build_report(kind, year, region, preferences)
        except (ValueError, KeyError, TypeError):
            logging.getLogger(__name__).exception("Unable to build synthetic report")
            return empty_report(
                "Unable to load the sample report. Change a filter to retry.",
                preferences,
            )
