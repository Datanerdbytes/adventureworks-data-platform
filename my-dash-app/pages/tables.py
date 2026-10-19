import dash
from dash import Input, Output, callback, dcc, html
from components import card, field, grid, heading
from data import grid_options
from dash.exceptions import PreventUpdate
from flask import current_app
from revenue_kpis import warehouse_location
from warehouse_tables import (
    TABLES,
    MAX_PREVIEW_ROWS,
    load_table_preview,
    preview_columns,
)

dash.register_page(__name__, path="/tables", title="Tables | AdventureWorks")


def layout():
    return html.Div(
        [
            heading(
                "Tables", "Explore read-only previews from the analytics warehouse."
            ),
            html.Div(
                [
                    field(
                        "Warehouse table",
                        dcc.Dropdown(
                            [
                                {"label": f"{name} · {spec['table']}", "value": name}
                                for name, spec in TABLES.items()
                            ],
                            "Products",
                            id="tables-selector",
                            clearable=False,
                            persistence=True,
                        ),
                    ),
                    field(
                        "Search loaded rows",
                        dcc.Input(
                            id="tables-search",
                            type="search",
                            placeholder="Search this warehouse preview…",
                            name="tables-search",
                            autoComplete="off",
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
    Input("app-location", "pathname"),
)
def populate(name, search, preferences, pathname="/tables"):
    if pathname != "/tables":
        raise PreventUpdate
    preferences = preferences if isinstance(preferences, dict) else {}
    options = grid_options(
        preferences.get("pageSize", 10), search if isinstance(search, str) else ""
    )
    if not isinstance(name, str) or name not in TABLES:
        return [], [], options, "Choose a warehouse table to preview."
    columns = preview_columns(name)
    try:
        project, dataset = warehouse_location()
        result = load_table_preview(project, dataset, name)
        rows = result["rows"]
        source = f"{project}.{dataset}.{TABLES[name]['table']}"
        if not rows:
            message = f"No rows available in {source}."
        else:
            scope = (
                f"First {MAX_PREVIEW_ROWS:,} rows; more rows exist"
                if result["capped"]
                else f"{len(rows):,} rows"
            )
            message = f"{source} · {scope} · One row per {TABLES[name]['grain']}. Search, filters and sorting apply to loaded rows. Cached for up to 60 seconds."
        return rows, columns, options, message
    except Exception as error:
        current_app.logger.warning(
            "Warehouse table preview failed (%s)", type(error).__name__
        )
        return (
            [],
            columns,
            options,
            "Warehouse preview is unavailable. Check warehouse access or choose another table to retry.",
        )
