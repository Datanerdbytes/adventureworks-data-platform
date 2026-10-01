import dash
from dash import Input, Output, State, callback, clientside_callback, dcc, html
from components import card, details, field, heading

dash.register_page(__name__, path="/settings", title="Settings | AdventureWorks")


def layout():
    return html.Div(
        [
            heading("Settings", "Make this workspace feel like yours."),
            html.Div(
                [
                    card(
                        "Project information",
                        [
                            details(),
                            html.P(
                                "This local demo does not connect to your warehouse or run pipelines.",
                                className="muted",
                            ),
                        ],
                    ),
                    card(
                        "Display preferences",
                        [
                            html.P(
                                "Saved in this browser on this device.",
                                className="muted",
                            ),
                            field(
                                "Rows per table page",
                                dcc.Dropdown(
                                    [10, 20, 50],
                                    id="settings-page-size",
                                    clearable=False,
                                ),
                            ),
                            html.Button(
                                "Toggle sidebar collapse",
                                id="settings-collapse",
                                className="button",
                            ),
                            html.P(
                                id="settings-status", role="status", className="muted"
                            ),
                        ],
                    ),
                ],
                className="settings-grid",
            ),
        ]
    )


@callback(
    Output("settings-page-size", "value"),
    Input("app-location", "pathname"),
    State("display-preferences", "data"),
)
def hydrate(path, preferences):
    if path != "/settings":
        raise dash.exceptions.PreventUpdate
    return (preferences or {}).get("pageSize", 10)


clientside_callback(
    """function(size, current) {
    if (![10,20,50].includes(size)) return window.dash_clientside.no_update;
    return {...(current || {}), pageSize: size};
}""",
    Output("display-preferences", "data"),
    Input("settings-page-size", "value"),
    State("display-preferences", "data"),
    prevent_initial_call=True,
)

clientside_callback(
    """function(prefs) {return 'Tables show ' + ((prefs || {}).pageSize || 10) + ' rows per page.';}""",
    Output("settings-status", "children"),
    Input("display-preferences", "data"),
)
