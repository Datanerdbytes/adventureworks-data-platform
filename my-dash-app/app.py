"""Local demo entrypoint: uv run python my-dash-app/app.py."""

from dash import Dash, Input, Output, clientside_callback, dcc, html, page_container
from flask import Flask, Response, g, has_request_context, render_template
from auth import install_auth
from user_admin import is_admin
from components import icon
from analytics import REPORTS
from revenue_kpis import init_kpi_cache
from theme import css_tokens, theme_script

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
    assets_ignore=r"auth\.js",
)


@server.get("/theme.css")
def theme_css():
    return Response(css_tokens(), mimetype="text/css")


app.index_string = app.index_string.replace(
    "{%css%}",
    theme_script()
    + '<link rel="stylesheet" href="/theme.css"><script src="/assets/auth.js"></script>{%css%}',
)

app.index_string = app.index_string.replace(
    "<body>", '<body class="auth-blocked">'
).replace(
    "{%app_entry%}",
    '<section id="auth-startup" role="status"><h1>Connecting to Analytics</h1>'
    '<p id="auth-status">Verifying your session…</p></section>{%app_entry%}',
)
app.renderer = "window.awAuthStart(function() { new DashRenderer(); });"


def serve_layout():
    username = (
        getattr(g, "account_username", "Member") if has_request_context() else "Member"
    )
    user = getattr(g, "auth_user", {}) if has_request_context() else {}
    can_admin = is_admin(user)
    role = (
        "Owner"
        if (user.get("app_metadata") or {}).get("qe_owner") is True
        else "Admin" if can_admin else "Member"
    )
    initials = "".join(
        part[0] for part in username.replace("@", " ").replace(".", " ").split()[:2]
    ).upper()
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
                            *(
                                [
                                    dcc.Link(
                                        [
                                            icon("settings"),
                                            html.Span(
                                                "User Management",
                                                className="nav-label",
                                            ),
                                        ],
                                        href="/admin/users",
                                        className="nav-link",
                                        title="User Management",
                                    )
                                ]
                                if can_admin
                                else []
                            ),
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
                                                "Sign Out",
                                                id="auth-sign-out",
                                                className="account-option",
                                            ),
                                            html.P(
                                                "Signed in with Supabase. Account access is verified by the server.",
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
                                                    html.Small(
                                                        role.replace("_", " ").title()
                                                    ),
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
      report && key === 'dashboard' ? 'Dashboard / ' + report : (key === 'workspace' ? 'Workspace Overview' : (path === '/admin/users' ? 'User Management' : (keys.includes(key) ? key[0].toUpperCase()+key.slice(1) : 'Page not found')))];
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
