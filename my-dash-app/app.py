"""Local demo entrypoint: uv run python my-dash-app/app.py."""

from pathlib import Path

from dash import Dash, Input, Output, clientside_callback, dcc, html, page_container
from dotenv import load_dotenv
from flask import Flask, Response, redirect, request
from components import icon
from analytics import REPORTS
from revenue_kpis import init_kpi_cache
from theme import css_tokens, theme_script

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

server = Flask(__name__)
init_kpi_cache(server)

# Every uncached request wakes the container on Vercel, so let the edge CDN
# serve Dash's static bundles and icons for the life of the deployment.
STATIC_CACHE_HEADER = "public, max-age=86400, s-maxage=86400"


@server.after_request
def cache_static_responses(response):
    path = request.path
    if path.startswith("/assets/") or path.startswith("/_dash-component-suite"):
        response.headers["Cache-Control"] = STATIC_CACHE_HEADER
    return response


@server.get("/")
def index():
    return redirect("/dashboard")


app = Dash(
    __name__,
    server=server,
    use_pages=True,
    suppress_callback_exceptions=True,
    title="AdventureWorks Analytics",
    update_title=None,
)


@server.get("/theme.css")
def theme_css():
    response = Response(css_tokens(), mimetype="text/css")
    response.headers["Cache-Control"] = "public, max-age=300, s-maxage=86400"
    return response


app.index_string = app.index_string.replace(
    "{%css%}",
    theme_script() + '<link rel="stylesheet" href="/theme.css">{%css%}',
)


def serve_layout():
    links = [
        ("workspace", "Workspace Overview"),
        ("dashboard", "Dashboard"),
        ("monitoring", "Monitoring"),
        ("tables", "Tables"),
        ("settings", "Settings"),
    ]
    return html.Div(
        [
            dcc.Location(id="app-location"),
            dcc.Store(
                id="display-preferences", storage_type="local", data={"pageSize": 10}
            ),
            dcc.Store(id="sidebar-preference", storage_type="local", data=False),
            dcc.Store(id="theme-apply"),
            html.A("Skip to content", href="#main-content", className="skip-link"),
            html.Header(
                [
                    html.Button(
                        icon("menu"),
                        id="mobile-menu",
                        className="icon-button mobile-only",
                        **{
                            "aria-label": "Open navigation",
                            "aria-expanded": "false",
                            "aria-controls": "app-sidebar",
                        },
                    ),
                    dcc.Link(
                        [
                            html.Span("AW", className="brand-mark"),
                            html.Span(
                                [
                                    html.Strong("AdventureWorks"),
                                    html.Small("ANALYTICS"),
                                ],
                                className="brand-name",
                            ),
                        ],
                        href="/dashboard",
                        className="brand",
                    ),
                ],
                className="app-header",
            ),
            html.Button(
                id="sidebar-backdrop", tabIndex=-1, **{"aria-label": "Close navigation"}
            ),
            html.Aside(
                [
                    html.Button(
                        [icon("close"), html.Span("Close navigation")],
                        id="mobile-close",
                        className="button mobile-only",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Small(
                                        "WORKSPACE", className="eyebrow nav-label"
                                    ),
                                    html.Button(
                                        html.Img(
                                            src="/assets/icons/sidebar-chevron.svg",
                                            alt="",
                                        ),
                                        id="sidebar-toggle",
                                        className="sidebar-collapse-toggle",
                                        title="Collapse Sidebar",
                                        **{
                                            "aria-label": "Collapse Sidebar",
                                            "aria-controls": "app-sidebar",
                                            "aria-expanded": "true",
                                        },
                                    ),
                                ],
                                className="workspace-heading",
                            ),
                            html.Div(
                                [
                                    html.Span("A", className="project-icon"),
                                    html.Strong(
                                        "AdventureWorks Analytics",
                                        className="workspace-name nav-label",
                                        title="AdventureWorks Analytics",
                                    ),
                                ],
                                className="workspace-card",
                            ),
                        ]
                    ),
                    html.P("PROJECT", className="eyebrow nav-label"),
                    html.Nav(
                        [
                            dcc.Link(
                                [
                                    icon("dashboard"),
                                    html.Span(
                                        "Workspace Overview", className="nav-label"
                                    ),
                                ],
                                href="/workspace",
                                id="nav-workspace",
                                className="nav-link",
                                title="Workspace Overview",
                            ),
                            html.Div(
                                [
                                    dcc.Link(
                                        [
                                            icon("dashboard"),
                                            html.Span(
                                                "Dashboard", className="nav-label"
                                            ),
                                        ],
                                        href="/dashboard",
                                        id="nav-dashboard",
                                        className="nav-link",
                                        title="Dashboard",
                                    ),
                                    html.Button(
                                        "⌄",
                                        id="dashboard-submenu-toggle",
                                        className="submenu-toggle",
                                        title="Dashboard reports",
                                        **{
                                            "aria-label": "Toggle dashboard reports",
                                            "aria-expanded": "false",
                                            "aria-controls": "dashboard-submenu",
                                        },
                                    ),
                                ],
                                className="dashboard-nav-row",
                            ),
                            html.Div(
                                [
                                    dcc.Link(
                                        label,
                                        href=f"/dashboard/{kind}",
                                        className="subnav-link",
                                        title=title,
                                        id=f"nav-report-{kind}",
                                    )
                                    for kind, (title, label, _) in REPORTS.items()
                                ],
                                id="dashboard-submenu",
                                hidden=True,
                            ),
                            *[
                                dcc.Link(
                                    [
                                        icon(key),
                                        html.Span(label, className="nav-label"),
                                    ],
                                    href=f"/{key}",
                                    id=f"nav-{key}",
                                    className="nav-link",
                                    title=label,
                                )
                                for key, label in links
                                if key not in {"dashboard", "workspace"}
                            ],
                        ],
                        className="sidebar-navigation",
                        **{"aria-label": "Main navigation"},
                    ),
                    html.Div(
                        [
                            html.Span(
                                "DA",
                                className="profile-avatar",
                                **{"aria-hidden": "true"},
                            ),
                            html.Div(
                                [
                                    html.Span(
                                        "DEMO ACCOUNT", className="eyebrow nav-label"
                                    ),
                                    html.Strong(
                                        "Demo Analyst",
                                        className="profile-name nav-label",
                                    ),
                                    html.Span(
                                        "demo@adventureworks.local",
                                        className="profile-email nav-label",
                                    ),
                                ],
                                className="profile-details",
                            ),
                        ],
                        className="sidebar-profile",
                    ),
                ],
                id="app-sidebar",
            ),
            html.Main(
                [
                    html.Div(
                        [
                            html.Span("Workspace"),
                            html.Span("/"),
                            html.Span(id="page-breadcrumb"),
                        ],
                        className="breadcrumb",
                    ),
                    html.Div(page_container, className="page-surface"),
                    html.Footer("AdventureWorks Analytics · Shared Analytics"),
                ],
                id="main-content",
                tabIndex=-1,
            ),
            html.Div(id="sidebar-sync", hidden=True),
        ],
        id="app-shell",
    )


app.layout = serve_layout
clientside_callback(
    """function(path) {
    const keys = ['workspace','dashboard','monitoring','tables','settings'];
    const key = (path || '').split('/')[1];
    const reports = {executive:'Revenue & Sales',wholesale:'Wholesale & Resellers',growth:'Growth & Seasonality',customers:'Customers & Regions'};
    const report = reports[(path || '').split('/')[2]];
    window.awSidebar?.navigate(path);
    return [...keys.map(k => k === key ? 'nav-link active' : 'nav-link'),
      report && key === 'dashboard' ? 'Dashboard / ' + report : (key === 'workspace' ? 'Workspace Overview' : (keys.includes(key) ? key[0].toUpperCase()+key.slice(1) : 'Page not found'))];
}""",
    *[
        Output(f"nav-{key}", "className")
        for key in ["workspace", "dashboard", "monitoring", "tables", "settings"]
    ],
    Output("page-breadcrumb", "children"),
    Input("app-location", "pathname"),
)
clientside_callback(
    """function(collapsed) {window.awSidebar?.apply(!!collapsed); return !!collapsed;}""",
    Output("sidebar-sync", "children"),
    Input("sidebar-preference", "data"),
)
clientside_callback(
    """function(preferences) {
        window.awTheme.apply(preferences || {});
        return preferences || {};
    }""",
    Output("theme-apply", "data"),
    Input("display-preferences", "data"),
)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=False)
