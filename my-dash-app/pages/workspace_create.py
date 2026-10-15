"""Focused platform workspace provisioning; database RPCs enforce owner eligibility."""

import re

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html
from dash.exceptions import PreventUpdate
from flask import abort, g, session
from components import heading
from governance import GovernanceError
from pages.workspace_admin import require_admin

PATH = "/workspace/admin/create"
FIELDS = ("name", "team", "purpose", "owner")
dash.register_page(__name__, path=PATH, title="Create workspace | AdventureWorks")


def require_platform_admin():
    try:
        require_admin()
    except GovernanceError as error:
        abort(error.status)
    if not g.workspace_context.get("platform_admin"):
        abort(403)


def layout():
    return html.Div(
        [
            heading(
                "Create workspace",
                "Set up a workspace and assign its first owner.",
                dcc.Link(
                    "← Workspace Admin", href="/workspace/admin", className="button"
                ),
            ),
            dcc.Loading(html.Div(id="workspace-create-content"), type="circle"),
            dcc.Location(id="workspace-create-reload", refresh=True),
        ],
        className="workspace-admin-page workspace-create-page",
    )


def form_field(label, key, help_text, *, required=False, limit=120):
    identifier = f"workspace-create-{key}"
    properties = dict(id=identifier, value="", maxLength=limit, required=required)
    control = (
        dbc.Textarea(**properties, rows=4)
        if key == "purpose"
        else dbc.Input(**properties, type="email" if key == "owner" else "text")
    )
    return html.Div(
        [
            html.Label(
                [label, html.Span("Required" if required else "Optional")],
                htmlFor=identifier,
                id=identifier + "-label",
            ),
            control,
            html.Small(help_text, id=identifier + "-help", className="admin-caption"),
            html.P(id=identifier + "-error", className="workspace-create-error"),
        ],
        className="field",
        role="group",
        **{
            "aria-labelledby": identifier + "-label",
            "aria-describedby": identifier + "-help " + identifier + "-error",
        },
    )


@callback(
    Output("workspace-create-content", "children"),
    Input("app-location", "pathname"),
)
def populate(path):
    if path != PATH:
        raise PreventUpdate
    require_platform_admin()
    return html.Div(
        [
            dbc.Form(
                [
                    html.Div(
                        [
                            html.H2("Workspace details"),
                            html.P(
                                "Choose a name your team will recognize.",
                                className="muted",
                            ),
                        ],
                        className="workspace-create-section-heading",
                    ),
                    html.Div(
                        [
                            form_field(
                                "Workspace name",
                                "name",
                                "Up to 120 characters.",
                                required=True,
                            ),
                            form_field(
                                "Responsible team",
                                "team",
                                "The team responsible for this workspace.",
                                required=True,
                            ),
                        ],
                        className="admin-form-row",
                    ),
                    form_field(
                        "Purpose",
                        "purpose",
                        "Describe what this workspace is for. Up to 1,000 characters.",
                        limit=1000,
                    ),
                    html.Div(
                        [
                            html.H2("Initial owner"),
                            html.P(
                                "This person will manage workspace details and member access.",
                                className="muted",
                            ),
                        ],
                        className="workspace-create-section-heading workspace-create-owner",
                    ),
                    form_field(
                        "Owner email",
                        "owner",
                        "Use the email of an existing account with a verified email address.",
                        required=True,
                        limit=254,
                    ),
                    html.Div(
                        id="workspace-create-status",
                        role="status",
                        **{"aria-live": "polite"},
                    ),
                    html.Div(
                        [
                            dcc.Link(
                                "Cancel", href="/workspace/admin", className="button"
                            ),
                            dbc.Button(
                                "Create workspace",
                                id="workspace-create-submit",
                                type="submit",
                                color=None,
                                className="button primary",
                            ),
                        ],
                        className="workspace-create-actions",
                    ),
                ],
                id="workspace-create-form",
                prevent_default_on_submit=True,
                className="admin-panel workspace-create-form",
            ),
            html.Aside(
                [
                    dbc.Badge(
                        "Platform administration",
                        color=None,
                        className="admin-role-badge",
                    ),
                    html.H2("A new space for your team"),
                    html.Ol(
                        [
                            html.Li(
                                [
                                    html.Strong("Assign an owner"),
                                    html.P(
                                        "The verified account receives Owner access when the workspace is created."
                                    ),
                                ]
                            ),
                            html.Li(
                                [
                                    html.Strong("Open your workspace"),
                                    html.P(
                                        "You’ll switch to the new workspace to manage its details and members."
                                    ),
                                ]
                            ),
                            html.Li(
                                [
                                    html.Strong("Bring in your team"),
                                    html.P(
                                        "Share its registration link and review verified access requests in Workspace Admin."
                                    ),
                                ]
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Strong("Shared analytics"),
                            html.P(
                                "Each workspace manages its own membership. All workspaces use the same AdventureWorks analytics dataset."
                            ),
                        ],
                        className="admin-help",
                    ),
                ],
                className="workspace-create-guide",
                **{"aria-label": "Workspace setup guide"},
            ),
        ],
        className="workspace-create-grid",
    )


@callback(
    Output("workspace-create-status", "children"),
    Output("workspace-create-reload", "href"),
    *[Output(f"workspace-create-{key}", "invalid") for key in FIELDS],
    *[Output(f"workspace-create-{key}-error", "children") for key in FIELDS],
    Input("workspace-create-form", "n_submit"),
    *[State(f"workspace-create-{key}", "value") for key in FIELDS],
    prevent_initial_call=True,
    running=[(Output("workspace-create-submit", "disabled"), True, False)],
)
def create_workspace(submits, name, team, purpose, owner):
    if not submits:
        raise PreventUpdate
    require_platform_admin()
    values = [
        value.strip() if isinstance(value, str) else ""
        for value in (name, team, purpose, owner)
    ]
    name, team, purpose, owner = values
    errors = [
        (
            "Enter a workspace name (up to 120 characters)."
            if not name or len(name) > 120
            else ""
        ),
        (
            "Enter a responsible team (up to 120 characters)."
            if not team or len(team) > 120
            else ""
        ),
        "Keep the purpose within 1,000 characters." if len(purpose) > 1000 else "",
        (
            "Enter a valid owner email address."
            if len(owner) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", owner)
            else ""
        ),
    ]
    if any(errors):
        return (
            dbc.Alert("Check the highlighted fields and try again.", color="danger"),
            dash.no_update,
            *[bool(error) for error in errors],
            *errors,
        )
    try:
        new_id = g.governance.rpc(
            "create_workspace",
            p_name=name,
            p_team=team,
            p_purpose=purpose,
            p_owner_email=owner,
        )
        session["workspace_id"] = new_id
        return (
            dbc.Alert("Workspace created. Opening Workspace Admin…", color="success"),
            "/workspace/admin",
            *([False] * 4),
            *([""] * 4),
        )
    except GovernanceError as error:
        if error.status in (401, 403, 503):
            abort(error.status)
        return (
            dbc.Alert(str(error), color="danger"),
            dash.no_update,
            *([False] * 4),
            *([""] * 4),
        )
