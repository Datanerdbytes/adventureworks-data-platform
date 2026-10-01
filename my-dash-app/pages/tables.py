import dash
from dash import Input, Output, callback, dcc, html
from components import card, field, grid, heading
from data import table_rows, grid_options

dash.register_page(__name__, path="/tables", title="Tables | AdventureWorks")


def layout():
    return html.Div(
        [
            heading(
                "Tables", "Explore a small, representative sample of your warehouse."
            ),
            html.Div(
                [
                    field(
                        "Sample table",
                        dcc.Dropdown(
                            ["Products", "Customers", "Sales"],
                            "Products",
                            id="tables-selector",
                            clearable=False,
                            persistence=True,
                        ),
                    ),
                    field(
                        "Search all columns",
                        dcc.Input(
                            id="tables-search",
                            type="search",
                            placeholder="Search sample records…",
                            debounce=True,
                        ),
                    ),
                ],
                className="filters",
            ),
            card(
                "Data preview",
                [grid("tables-grid")],
                html.Span("Read only", className="badge"),
            ),
            html.P(id="tables-status", role="status", className="muted"),
        ]
    )


@callback(
    Output("tables-grid", "rowData"),
    Output("tables-grid", "columnDefs"),
    Output("tables-grid", "dashGridOptions"),
    Output("tables-status", "children"),
    Input("tables-selector", "value"),
    Input("tables-search", "value"),
    Input("display-preferences", "data"),
)
def populate(name, search, preferences):
    try:
        rows = table_rows(name)
        return (
            rows,
            [{"field": key} for key in rows[0]] if rows else [],
            grid_options((preferences or {}).get("pageSize", 10), search),
            (
                f"{len(rows)} synthetic records · {name}"
                if rows
                else "No sample records available."
            ),
        )
    except (ValueError, KeyError, TypeError):
        return (
            [],
            [],
            grid_options(),
            "Unable to load this sample table. Choose another table to retry.",
        )
