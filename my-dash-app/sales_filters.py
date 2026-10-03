"""Shared, namespaced warehouse filter controls and catalog validation."""

from dash import Input, Output, State, callback, dcc, html
from dash.exceptions import PreventUpdate
from components import field
from revenue_kpis import load_filter_catalog, warehouse_location

ALL = "__all__"
FIELDS = {
    "year": ("Calendar year", "calendar_year"),
    "quarter": ("Quarter", "calendar_quarter_name"),
    "channel": ("Sales channel", "sales_channel"),
    "category": ("Product category", "product_category"),
    "subcategory": ("Product subcategory", "product_subcategory"),
}


def filter_layout(prefix):
    controls = [
        field(
            label,
            dcc.Dropdown(
                id=f"{prefix}-{name}",
                options=[{"label": "All", "value": ALL}],
                value=ALL,
                clearable=False,
                persistence=True,
                persistence_type="session",
            ),
        )
        for name, (label, _) in FIELDS.items()
    ]
    return html.Div(
        [
            dcc.Store(id=f"{prefix}-catalog"),
            dcc.Store(id=f"{prefix}-load", data=True),
            html.Div(
                [
                    html.Div(controls[:2], className="executive-time-filter"),
                    *controls[2:],
                ],
                className="executive-global-filters",
            ),
            html.P(id=f"{prefix}-filter-status", role="status", className="muted"),
        ]
    )


def valid_values(rows, selections):
    """Reset invalid persisted values, including a child outside its category."""
    choices, values = [], []
    for index, (_, column) in enumerate(FIELDS.values()):
        allowed = sorted(
            {
                row[column]
                for row in rows
                if row[column] is not None
                and (
                    index != 4
                    or values[3] == ALL
                    or row["product_category"] == values[3]
                )
            }
        )
        choices.append(
            [{"label": "All", "value": ALL}]
            + [{"label": str(v), "value": v} for v in allowed]
        )
        values.append(selections[index] if selections[index] in allowed else ALL)
    return choices, values


def register_filters(prefix):
    @callback(
        Output(f"{prefix}-catalog", "data"),
        Output(f"{prefix}-filter-status", "children"),
        Input(f"{prefix}-load", "data"),
    )
    def load_catalog(_):
        try:
            return load_filter_catalog(*warehouse_location()), ""
        except Exception:
            return None, "Unable to load warehouse filters. Reload this page to retry."

    @callback(
        *[Output(f"{prefix}-{name}", "options") for name in FIELDS],
        *[Output(f"{prefix}-{name}", "value") for name in FIELDS],
        Input(f"{prefix}-catalog", "data"),
        Input(f"{prefix}-category", "value"),
        *[State(f"{prefix}-{name}", "value") for name in FIELDS if name != "category"],
    )
    def restore(catalog, category, year, quarter, channel, subcategory):
        if catalog is None:
            raise PreventUpdate
        choices, values = valid_values(
            catalog, [year, quarter, channel, category, subcategory]
        )
        return (*choices, *values)
