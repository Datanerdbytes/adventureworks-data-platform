"""Browser-local preferences, grouped into accessible desktop-style settings."""

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, clientside_callback, dcc, html
from dash.exceptions import PreventUpdate
from components import details, heading

dash.register_page(__name__, path="/settings", title="Settings | AdventureWorks")


def choices(identifier, options):
    return html.Div(
        dcc.RadioItems(
            id=identifier,
            options=[{"label": label, "value": value} for label, value in options],
            className="settings-segments",
        ),
        role="radiogroup",
        **{
            "aria-labelledby": identifier + "-label",
            "aria-describedby": identifier + "-hint",
        },
    )


def switch(identifier, title):
    return dbc.Switch(
        id=identifier,
        label=title,
        value=None,
        class_name="settings-switch",
        label_class_name="settings-visually-hidden",
    )


def row(identifier, title, hint, control):
    return html.Div(
        [
            html.Div(
                [
                    html.P(
                        title, id=identifier + "-label", className="settings-row-title"
                    ),
                    html.P(
                        hint, id=identifier + "-hint", className="settings-row-hint"
                    ),
                ],
                className="settings-row-copy",
            ),
            html.Div(control, className="settings-row-control"),
        ],
        className="settings-row",
    )


def group(identifier, title, description, rows):
    return html.Section(
        [
            html.Div(
                [html.H2(title, id=identifier + "-heading"), html.P(description)],
                className="settings-group-heading",
            ),
            dbc.Card(rows, class_name="settings-group-card"),
        ],
        id=identifier,
        className="settings-group",
        **{"aria-labelledby": identifier + "-heading"},
    )


def option_row(identifier, title, hint, options):
    return row(identifier, title, hint, choices(identifier, options))


def layout(**_query):
    sections = [
        ("appearance", "Appearance"),
        ("display", "Layout & tables"),
        ("accessibility", "Accessibility"),
        ("data", "Data & exports"),
        ("notifications", "Notifications"),
        ("about", "About"),
    ]
    return html.Div(
        [
            heading(
                "Settings",
                "Personalize your workspace. Changes are saved automatically in this browser.",
            ),
            html.Div(
                [
                    html.Nav(
                        [
                            html.P("Preferences", className="settings-nav-label"),
                            *[
                                html.A(
                                    label,
                                    href="#settings-section-" + key,
                                    className="settings-section-link",
                                )
                                for key, label in sections
                            ],
                        ],
                        className="settings-section-nav",
                        **{"aria-label": "Settings sections"},
                    ),
                    html.Div(
                        [
                            group(
                                "settings-section-appearance",
                                "Appearance",
                                "Choose how your workspace looks.",
                                [
                                    option_row(
                                        "settings-theme",
                                        "Color scheme",
                                        "System follows your device appearance. Light is the default.",
                                        [
                                            ("Light", "light"),
                                            ("Dark", "dark"),
                                            ("System", "system"),
                                        ],
                                    ),
                                    option_row(
                                        "settings-density",
                                        "UI density",
                                        "Adjust spacing between controls and content.",
                                        [
                                            ("Compact", "compact"),
                                            ("Comfortable", "comfortable"),
                                            ("Spacious", "spacious"),
                                        ],
                                    ),
                                    option_row(
                                        "settings-font-size",
                                        "Text size",
                                        "Set the base text size for the workspace.",
                                        [
                                            ("Small", "small"),
                                            ("Default", "default"),
                                            ("Large", "large"),
                                        ],
                                    ),
                                ],
                            ),
                            group(
                                "settings-section-display",
                                "Layout & tables",
                                "Keep navigation and table views comfortable.",
                                [
                                    row(
                                        "settings-collapse",
                                        "Collapse sidebar",
                                        "Show a compact navigation rail on desktop.",
                                        switch("settings-collapse", "Collapse sidebar"),
                                    ),
                                    option_row(
                                        "settings-page-size",
                                        "Rows per table page",
                                        "Applies to tables that support this preference. Member directory pages stay at 10 rows.",
                                        [("10", 10), ("20", 20), ("50", 50)],
                                    ),
                                    html.P(
                                        id="settings-status",
                                        role="status",
                                        className="settings-save-status",
                                    ),
                                ],
                            ),
                            group(
                                "settings-section-accessibility",
                                "Accessibility",
                                "Make motion and interactions easier to follow.",
                                [
                                    option_row(
                                        "settings-reduce-motion",
                                        "Reduce motion",
                                        "Limit animations, or follow your device's reduced-motion setting.",
                                        [
                                            ("Off", "off"),
                                            ("On", "on"),
                                            ("System", "system"),
                                        ],
                                    ),
                                ],
                            ),
                            html.Section(
                                [
                                    html.Div(
                                        [
                                            html.H2(
                                                "Data & exports",
                                                id="settings-section-data-heading",
                                            ),
                                            html.P(
                                                "These preferences are saved for future support. Reports and exports currently use their own controls."
                                            ),
                                        ],
                                        className="settings-group-heading",
                                    ),
                                    dbc.Card(
                                        [
                                            option_row(
                                                "settings-default-chart-type",
                                                "Default chart type",
                                                "Preferred starting view for charts.",
                                                [
                                                    ("Line", "line"),
                                                    ("Bar", "bar"),
                                                    ("Dual axis", "dual"),
                                                ],
                                            ),
                                            option_row(
                                                "settings-number-format",
                                                "Number formatting",
                                                "Compact: 128.4K · Full: 128,400.",
                                                [
                                                    ("Compact", "compact"),
                                                    ("Full", "full"),
                                                ],
                                            ),
                                            option_row(
                                                "settings-currency",
                                                "Currency display",
                                                "Preferred currency presentation. Warehouse amounts are USD.",
                                                [("USD", "USD"), ("Local", "local")],
                                            ),
                                        ],
                                        class_name="settings-group-card",
                                    ),
                                    html.H3(
                                        "Export defaults",
                                        className="settings-subheading",
                                    ),
                                    dbc.Card(
                                        [
                                            option_row(
                                                "settings-export-format",
                                                "File format",
                                                "Preferred format for downloads.",
                                                [("CSV", "CSV"), ("JSON", "JSON")],
                                            ),
                                            row(
                                                "settings-include-filters",
                                                "Include filters in filenames",
                                                "Add the selected filters to downloaded filenames.",
                                                switch(
                                                    "settings-include-filters",
                                                    "Include filters in filenames",
                                                ),
                                            ),
                                        ],
                                        class_name="settings-group-card",
                                    ),
                                ],
                                id="settings-section-data",
                                className="settings-group",
                                **{"aria-labelledby": "settings-section-data-heading"},
                            ),
                            group(
                                "settings-section-notifications",
                                "Notifications",
                                "Saved preferences only. Demo monitoring does not send alerts; report messages currently use a fixed level of detail.",
                                [
                                    row(
                                        "settings-pipeline-alerts",
                                        "Pipeline alerts",
                                        "Your preference for pipeline notifications.",
                                        switch(
                                            "settings-pipeline-alerts",
                                            "Pipeline alerts",
                                        ),
                                    ),
                                    option_row(
                                        "settings-status-verbosity",
                                        "Message detail",
                                        "Preferred level of explanation in status messages.",
                                        [("Brief", "brief"), ("Detailed", "detailed")],
                                    ),
                                ],
                            ),
                            group(
                                "settings-section-about",
                                "About",
                                "Information about the bundled sample data.",
                                [
                                    html.Div(
                                        details(), className="settings-project-details"
                                    )
                                ],
                            ),
                        ],
                        className="settings-section-content",
                    ),
                ],
                className="settings-workspace",
            ),
        ],
        className="settings-page",
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
        prefs.get("pipelineAlerts", "on") == "on",
        prefs.get("statusVerbosity", "brief"),
        prefs.get("exportFormat", "CSV"),
        prefs.get("includeFilters", "off") == "on",
        prefs.get("pageSize", 10),
    )


clientside_callback(
    """
    function(theme, density, reduceMotion, fontSize, defaultChartType, numberFormat,
             currency, pipelineAlerts, statusVerbosity, exportFormat, includeFilters,
             pageSize, current) {
        // Wait for the settings hydration callback before saving anything.
        if ([theme, density, reduceMotion, fontSize, defaultChartType, numberFormat,
             currency, pipelineAlerts, statusVerbosity, exportFormat, includeFilters,
             pageSize].some(value => value == null)) {
            return window.dash_clientside.no_update;
        }

        var defaults = {
            theme: 'light', density: 'comfortable', reduceMotion: 'off',
            fontSize: 'default', defaultChartType: 'line', numberFormat: 'compact',
            currency: 'USD', pipelineAlerts: 'on', statusVerbosity: 'brief',
            exportFormat: 'CSV', includeFilters: 'off', pageSize: 10
        };
        var next = {
            ...(current || {}),
            theme: theme,
            density: density,
            reduceMotion: reduceMotion,
            fontSize: fontSize,
            defaultChartType: defaultChartType,
            numberFormat: numberFormat,
            currency: currency,
            pipelineAlerts: pipelineAlerts ? "on" : "off",
            statusVerbosity: statusVerbosity,
            exportFormat: exportFormat,
            includeFilters: includeFilters ? "on" : "off",
            pageSize: pageSize,
        };
        // Hydrating the controls must not write defaults into browser storage.
        if (Object.keys(defaults).every(key =>
            next[key] === ((current || {})[key] ?? defaults[key]))) {
            return window.dash_clientside.no_update;
        }
        return next;
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
    """function(prefs) {return 'Default table page size: ' + ((prefs || {}).pageSize || 10) + ' rows.';}""",
    Output("settings-status", "children"),
    Input("display-preferences", "data"),
)


@callback(
    Output("settings-collapse", "value"),
    Input("app-location", "pathname"),
    State("sidebar-preference", "data"),
)
def hydrate_sidebar(path, collapsed):
    if path != "/settings":
        raise PreventUpdate
    return bool(collapsed)


@callback(
    Output("sidebar-preference", "data"),
    Input("settings-collapse", "value"),
    State("sidebar-preference", "data"),
    prevent_initial_call=True,
)
def toggle_sidebar(collapsed, current):
    if collapsed is None or collapsed == bool(current):
        raise PreventUpdate
    return bool(collapsed)
