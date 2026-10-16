import dash
from dash import Input, Output, State, callback, clientside_callback, dcc, html
from dash.exceptions import PreventUpdate
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
                        [details()],
                    ),
                    card(
                        "Appearance",
                        [
                            html.P(
                                "Saved in this browser on this device.",
                                className="muted",
                            ),
                            field(
                                "Color scheme",
                                dcc.Dropdown(
                                    [
                                        {"label": "Light", "value": "light"},
                                        {"label": "Dark", "value": "dark"},
                                        {"label": "System", "value": "system"},
                                    ],
                                    id="settings-theme",
                                    clearable=False,
                                ),
                            ),
                            field(
                                "UI density",
                                dcc.Dropdown(
                                    [
                                        {"label": "Compact", "value": "compact"},
                                        {
                                            "label": "Comfortable",
                                            "value": "comfortable",
                                        },
                                        {"label": "Spacious", "value": "spacious"},
                                    ],
                                    id="settings-density",
                                    clearable=False,
                                ),
                            ),
                            field(
                                "Font size",
                                dcc.Dropdown(
                                    [
                                        {"label": "Small", "value": "small"},
                                        {"label": "Default", "value": "default"},
                                        {"label": "Large", "value": "large"},
                                    ],
                                    id="settings-font-size",
                                    clearable=False,
                                ),
                            ),
                        ],
                    ),
                    card(
                        "Accessibility",
                        [
                            html.P(
                                "Reduces motion and improves readability.",
                                className="muted",
                            ),
                            field(
                                "Reduce motion",
                                dcc.Dropdown(
                                    [
                                        {"label": "Off", "value": "off"},
                                        {"label": "On", "value": "on"},
                                        {"label": "System", "value": "system"},
                                    ],
                                    id="settings-reduce-motion",
                                    clearable=False,
                                ),
                            ),
                        ],
                    ),
                    card(
                        "Data preferences",
                        [
                            field(
                                "Default chart type",
                                dcc.Dropdown(
                                    [
                                        {"label": "Line", "value": "line"},
                                        {"label": "Bar", "value": "bar"},
                                        {"label": "Dual axis", "value": "dual"},
                                    ],
                                    id="settings-default-chart-type",
                                    clearable=False,
                                ),
                            ),
                            field(
                                "Number formatting",
                                dcc.Dropdown(
                                    [
                                        {
                                            "label": "Compact (128.4K)",
                                            "value": "compact",
                                        },
                                        {
                                            "label": "Full precision ($128,400)",
                                            "value": "full",
                                        },
                                    ],
                                    id="settings-number-format",
                                    clearable=False,
                                ),
                            ),
                            field(
                                "Currency display",
                                dcc.Dropdown(
                                    [
                                        {"label": "USD", "value": "USD"},
                                        {"label": "Local", "value": "local"},
                                    ],
                                    id="settings-currency",
                                    clearable=False,
                                ),
                            ),
                        ],
                    ),
                    card(
                        "Notifications",
                        [
                            field(
                                "Pipeline alerts",
                                dcc.Dropdown(
                                    [
                                        {"label": "On", "value": "on"},
                                        {"label": "Off", "value": "off"},
                                    ],
                                    id="settings-pipeline-alerts",
                                    clearable=False,
                                ),
                            ),
                            field(
                                "Status message verbosity",
                                dcc.Dropdown(
                                    [
                                        {"label": "Brief", "value": "brief"},
                                        {"label": "Detailed", "value": "detailed"},
                                    ],
                                    id="settings-status-verbosity",
                                    clearable=False,
                                ),
                            ),
                        ],
                    ),
                    card(
                        "Export defaults",
                        [
                            field(
                                "Default export format",
                                dcc.Dropdown(
                                    [
                                        {"label": "CSV", "value": "CSV"},
                                        {"label": "JSON", "value": "JSON"},
                                    ],
                                    id="settings-export-format",
                                    clearable=False,
                                ),
                            ),
                            field(
                                "Include filters in filename",
                                dcc.Dropdown(
                                    [
                                        {"label": "Off", "value": "off"},
                                        {"label": "On", "value": "on"},
                                    ],
                                    id="settings-include-filters",
                                    clearable=False,
                                ),
                            ),
                        ],
                    ),
                    card(
                        "Display preferences",
                        [
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
    Output("settings-theme", "value"),
    Output("settings-density", "value"),
    Output("settings-reduce-motion", "value"),
    Output("settings-font-size", "value"),
    Output("settings-default-chart-type", "value"),
    Output("settings-number-format", "value"),
    Output("settings-currency", "value"),
    Output("settings-pipeline-alerts", "value"),
    Output("settings-status-verbosity", "value"),
    Output("settings-export-format", "value"),
    Output("settings-include-filters", "value"),
    Output("settings-page-size", "value"),
    Input("app-location", "pathname"),
    State("display-preferences", "data"),
)
def hydrate_all(path, preferences):
    if path != "/settings":
        raise PreventUpdate
    prefs = preferences or {}
    return (
        prefs.get("theme", "light"),
        prefs.get("density", "comfortable"),
        prefs.get("reduceMotion", "off"),
        prefs.get("fontSize", "default"),
        prefs.get("defaultChartType", "line"),
        prefs.get("numberFormat", "compact"),
        prefs.get("currency", "USD"),
        prefs.get("pipelineAlerts", "on"),
        prefs.get("statusVerbosity", "brief"),
        prefs.get("exportFormat", "CSV"),
        prefs.get("includeFilters", "off"),
        prefs.get("pageSize", 10),
    )


clientside_callback(
    """
    function(theme, density, reduceMotion, fontSize, defaultChartType, numberFormat,
             currency, pipelineAlerts, statusVerbosity, exportFormat, includeFilters,
             pageSize, current) {
        var body = document.body;
        var html = document.documentElement;

        // Remove all setting classes first
        body.classList.remove(
            'theme-dark',
            'font-size-small',
            'font-size-large',
            'density-compact',
            'density-spacious',
            'reduce-motion'
        );
        html.removeAttribute('data-theme');

        // Apply theme
        var isDark =
            theme === 'dark' ||
            (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
        if (isDark) {
            body.classList.add('theme-dark');
            html.setAttribute('data-theme', 'dark');
            var meta = document.querySelector('meta[name="theme-color"]');
            if (meta) meta.setAttribute('content', '#0F172A');
        } else {
            var meta = document.querySelector('meta[name="theme-color"]');
            if (meta) meta.setAttribute('content', '#fcfdff');
        }

        // Apply font size
        if (fontSize === 'small') body.classList.add('font-size-small');
        if (fontSize === 'large') body.classList.add('font-size-large');

        // Apply density
        if (density === 'compact') body.classList.add('density-compact');
        if (density === 'spacious') body.classList.add('density-spacious');

        // Apply reduce motion
        var isReduceMotion =
            reduceMotion === 'on' ||
            (reduceMotion === 'system' &&
                window.matchMedia('(prefers-reduced-motion: reduce)').matches);
        if (isReduceMotion) body.classList.add('reduce-motion');

        return {
            ...(current || {}),
            theme: theme,
            density: density,
            reduceMotion: reduceMotion,
            fontSize: fontSize,
            defaultChartType: defaultChartType,
            numberFormat: numberFormat,
            currency: currency,
            pipelineAlerts: pipelineAlerts,
            statusVerbosity: statusVerbosity,
            exportFormat: exportFormat,
            includeFilters: includeFilters,
            pageSize: pageSize,
        };
    }
    """,
    Output("display-preferences", "data"),
    Input("settings-theme", "value"),
    Input("settings-density", "value"),
    Input("settings-reduce-motion", "value"),
    Input("settings-font-size", "value"),
    Input("settings-default-chart-type", "value"),
    Input("settings-number-format", "value"),
    Input("settings-currency", "value"),
    Input("settings-pipeline-alerts", "value"),
    Input("settings-status-verbosity", "value"),
    Input("settings-export-format", "value"),
    Input("settings-include-filters", "value"),
    Input("settings-page-size", "value"),
    State("display-preferences", "data"),
)


clientside_callback(
    """function(prefs) {return 'Tables show ' + ((prefs || {}).pageSize || 10) + ' rows per page.';}""",
    Output("settings-status", "children"),
    Input("display-preferences", "data"),
)


@callback(
    Output("sidebar-preference", "data"),
    Input("settings-collapse", "n_clicks"),
    State("sidebar-preference", "data"),
    prevent_initial_call=True,
)
def toggle_sidebar(n_clicks, collapsed):
    if not n_clicks:
        raise PreventUpdate
    return not (collapsed or False)
