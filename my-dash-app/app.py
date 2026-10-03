"""Local demo entrypoint: uv run python my-dash-app/app.py."""

from dash import Dash, Input, Output, clientside_callback, dcc, html, page_container
from flask import Flask, Response, g, has_request_context, render_template
from auth import install_auth, configure_auth
from components import icon
from analytics import REPORTS
from revenue_kpis import init_kpi_cache
from theme import css_tokens

server = Flask(__name__)
install_auth(server)
init_kpi_cache(server)


@server.get("/")
def landing():
    return render_template("landing.html")


app = Dash(
    __name__,
    server=server,
    use_pages=True,
    suppress_callback_exceptions=True,
    title="AdventureWorks Analytics",
    update_title=None,
)
configure_auth(app)


@server.get("/theme.css")
def theme_css():
    return Response(css_tokens(), mimetype="text/css")


app.index_string = app.index_string.replace(
    "{%css%}", '<link rel="stylesheet" href="/theme.css">{%css%}'
)


def serve_layout():
    username = (
        getattr(g, "workspace_username", "Workspace member")
        if has_request_context()
        else "Workspace member"
    )
    initials = "".join(
        part[0] for part in username.replace("@", " ").replace(".", " ").split()[:2]
    ).upper()
    links = [
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
                    html.Div(
                        [
                            html.Span("Local workspace", className="workspace-label"),
                            html.Span(
                                "Demo data",
                                id="workspace-data-label",
                                className="badge demo",
                            ),
                            html.Span(
                                "AW",
                                className="avatar",
                                **{"aria-label": "AdventureWorks demo workspace"},
                            ),
                        ],
                        className="header-end",
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
                            html.Small("WORKSPACE", className="eyebrow nav-label"),
                            html.Div(
                                [
                                    html.Span("A", className="project-icon"),
                                    html.Div(
                                        [
                                            html.Strong("AdventureWorks"),
                                            html.Small("Local demo", className="muted"),
                                        ],
                                        className="nav-label",
                                    ),
                                ],
                                className="workspace-card",
                            ),
                        ]
                    ),
                    html.P("PROJECT", className="eyebrow nav-label"),
                    html.Nav(
                        [
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
                                if key != "dashboard"
                            ],
                        ],
                        className="sidebar-navigation",
                        **{"aria-label": "Main navigation"},
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span(className="status-dot"),
                                    html.Span("Demo workspace", className="nav-label"),
                                ],
                                className="sidebar-status",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Small("SIGNED IN AS"),
                                                    html.Strong(username),
                                                ],
                                                className="account-identity",
                                            ),
                                            dcc.Link(
                                                "Workspace settings",
                                                href="/settings",
                                                className="account-option",
                                            ),
                                            html.A(
                                                "Back to website",
                                                href="/",
                                                className="account-option",
                                            ),
                                            html.Button(
                                                "Toggle sidebar",
                                                id="sidebar-toggle",
                                                className="account-option",
                                                **{
                                                    "aria-controls": "app-sidebar",
                                                    "aria-expanded": "true",
                                                },
                                            ),
                                            html.P(
                                                "Signed in with your configured workspace credentials.",
                                                className="account-hint",
                                            ),
                                        ],
                                        id="account-menu",
                                        hidden=True,
                                    ),
                                    html.Button(
                                        [
                                            html.Span(
                                                initials,
                                                className="account-avatar",
                                                **{"aria-hidden": "true"},
                                            ),
                                            html.Span(
                                                [
                                                    html.Strong(username),
                                                    html.Small("Workspace member"),
                                                ],
                                                className="account-label nav-label",
                                            ),
                                            html.Img(
                                                src="/assets/icons/chevron.svg",
                                                alt="",
                                                className="account-chevron",
                                            ),
                                        ],
                                        id="account-toggle",
                                        className="account-toggle",
                                        title="Account",
                                        **{
                                            "aria-label": f"Account for {username}",
                                            "aria-expanded": "false",
                                            "aria-controls": "account-menu",
                                        },
                                    ),
                                ],
                                className="account-area",
                            ),
                        ],
                        className="sidebar-bottom",
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
                    html.Footer("AdventureWorks Analytics · Local demonstration"),
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
    const keys = ['dashboard','monitoring','tables','settings'];
    const key = (path || '').split('/')[1];
    const reports = {executive:'Revenue & Sales',wholesale:'Wholesale & Resellers',growth:'Growth & Seasonality',customers:'Customers & Regions'};
    const report = reports[(path || '').split('/')[2]];
    window.awSidebar?.navigate(path);
    return [...keys.map(k => k === key ? 'nav-link active' : 'nav-link'),
      report && key === 'dashboard' ? 'Dashboard / ' + report : (keys.includes(key) ? key[0].toUpperCase()+key.slice(1) : 'Page not found')];
}""",
    *[
        Output(f"nav-{key}", "className")
        for key in ["dashboard", "monitoring", "tables", "settings"]
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
    "function(path) { return path === '/dashboard/executive' ? 'Warehouse data' : ['/dashboard/wholesale', '/dashboard/growth'].includes(path) ? 'Warehouse data' : 'Demo data'; }",
    Output("workspace-data-label", "children"),
    Input("app-location", "pathname"),
)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=False)
