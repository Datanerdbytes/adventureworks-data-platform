"""Workspace provisioning UI. Database RPCs are the permission boundary."""

from datetime import datetime

import dash
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
from dash import Input, Output, State, callback, ctx, dcc, html
from dash.exceptions import PreventUpdate
from flask import abort, g, session, current_app
from components import field, heading
from governance import GovernanceError

dash.register_page(
    __name__, path="/workspace/admin", title="Workspace Administration | AdventureWorks"
)


def layout():
    return html.Div(
        [
            heading(
                "Workspace Administration",
                "Manage your workspace and the people who can access it.",
                dcc.Link("← Workspace Overview", href="/workspace", className="button"),
            ),
            html.Div(
                id="workspace-admin-status", role="status", **{"aria-live": "polite"}
            ),
            dcc.Store(id="workspace-admin-page-offset", data=0),
            dcc.Loading(html.Div(id="workspace-admin-content"), type="circle"),
            dcc.Location(id="workspace-admin-reload", refresh=True),
        ],
        className="workspace-admin-page",
    )


def require_admin():
    workspace = getattr(g, "workspace", None)
    if not workspace or workspace["role"] not in ("owner", "admin", "platform_admin"):
        raise GovernanceError("Workspace administration access denied.", 403)
    return workspace


def text_field(label, identifier, value="", max_length=120):
    if "purpose" in identifier:
        control = dbc.Textarea(id=identifier, value=value, maxLength=max_length, rows=3)
    else:
        control = dbc.Input(
            id=identifier,
            value=value,
            type="email" if "email" in identifier or "owner" in identifier else "text",
            maxLength=max_length,
        )
    return field(label, control)


def button(label, identifier, danger=False, disabled=False):
    return dbc.Button(
        label,
        id=identifier,
        n_clicks=0,
        disabled=disabled,
        color=None,
        className="button admin-danger" if danger else "button primary",
    )


def panel(title, description, children, wide=False, extra=None):
    return dbc.Card(
        [
            html.Div(
                [
                    html.Div([html.H2(title), html.P(description, className="muted")]),
                    extra,
                ],
                className="admin-panel-heading",
            ),
            *children,
        ],
        className="admin-panel admin-wide" if wide else "admin-panel",
    )


def role_field(label, identifier, roles):
    return field(
        label,
        dcc.Dropdown(
            id=identifier,
            options=[{"label": r.title(), "value": r} for r in roles],
            value="viewer",
            clearable=False,
        ),
    )


def activity_item(event):
    raw_date = event["created_at"]
    try:
        date = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).strftime(
            "%d %b %Y · %H:%M %Z"
        )
    except (ValueError, TypeError):
        date = raw_date
    actor = str(event.get("actor_id") or "System")
    return html.Li(
        [
            html.Div(
                [
                    html.Strong(event["action"].replace("_", " ").title()),
                    html.Time(date, dateTime=raw_date),
                ],
                className="admin-event-heading",
            ),
            html.Small("Actor: " + actor, className="muted"),
        ]
    )


@callback(
    Output("workspace-admin-content", "children"),
    Input("app-location", "pathname"),
    Input("workspace-admin-page-offset", "data"),
)
def populate(path, offset=None):
    if path != "/workspace/admin":
        raise PreventUpdate
    try:
        w = require_admin()
        offset = int(offset or 0)
        data = g.governance.rpc(
            "workspace_admin_data", p_workspace=w["id"], p_offset=offset
        )
        roles = ["viewer"] if w["role"] == "admin" else ["viewer", "admin", "owner"]
        members = data["members"]
        manageable = [
            m for m in members if w["role"] != "admin" or m["role"] == "viewer"
        ]
        approvals = data["approvals"]
        children = [
            html.Section(
                [
                    html.Div(
                        [
                            html.Small("CURRENT WORKSPACE", className="admin-eyebrow"),
                            html.H2(w["name"]),
                            html.Dl(
                                [
                                    html.Div(
                                        [
                                            html.Dt("Responsible Team"),
                                            html.Dd(w["responsible_team"]),
                                        ]
                                    ),
                                    html.Div(
                                        [
                                            html.Dt("Purpose"),
                                            html.Dd(w["purpose"] or "Not specified"),
                                        ]
                                    ),
                                ],
                                className="admin-workspace-details",
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            dbc.Badge(
                                w["role"].replace("_", " ").title(),
                                color=None,
                                className="admin-role-badge",
                            ),
                            html.Span(
                                [
                                    html.Strong(str(data["member_count"])),
                                    (
                                        " Member"
                                        if data["member_count"] == 1
                                        else " Members"
                                    ),
                                ]
                            ),
                            html.Span(
                                [
                                    html.Strong(str(data["approval_count"])),
                                    " Pending Approvals",
                                ]
                            ),
                            (
                                dbc.Button(
                                    "Edit Details",
                                    id="workspace-admin-edit",
                                    n_clicks=0,
                                    color=None,
                                    className="button",
                                )
                                if w["role"] in ("owner", "platform_admin")
                                else None
                            ),
                        ],
                        className="admin-workspace-meta",
                    ),
                ],
                className="admin-workspace-banner admin-wide",
            ),
        ]
        if w["role"] in ("owner", "platform_admin"):
            children.append(
                dbc.Modal(
                    [
                        dbc.ModalHeader(dbc.ModalTitle("Edit Workspace Details")),
                        dbc.ModalBody(
                            [
                                text_field(
                                    "Workspace Name", "workspace-admin-name", w["name"]
                                ),
                                text_field(
                                    "Responsible Team",
                                    "workspace-admin-team",
                                    w["responsible_team"],
                                ),
                                text_field(
                                    "Purpose",
                                    "workspace-admin-purpose",
                                    w["purpose"],
                                    1000,
                                ),
                            ]
                        ),
                        dbc.ModalFooter(
                            [
                                dbc.Button(
                                    "Cancel",
                                    id="workspace-admin-edit-cancel",
                                    n_clicks=0,
                                    color=None,
                                    className="button",
                                ),
                                button("Save Details", "workspace-admin-save"),
                            ]
                        ),
                    ],
                    id="workspace-admin-edit-modal",
                    is_open=False,
                    centered=True,
                    className="workspace-admin-page admin-edit-modal",
                    backdrop_class_name="admin-edit-backdrop",
                    fade=False,
                )
            )
        children.append(
            panel(
                "Awaiting Approval",
                "Verified users requesting access to this workspace.",
                [
                    field(
                        "Search Emails",
                        dbc.Input(
                            id="workspace-admin-request-search",
                            type="search",
                            placeholder="Search this batch",
                        ),
                    ),
                    dag.AgGrid(
                        id="workspace-admin-requests",
                        rowData=[
                            {**row, "grant_role": "viewer", "decision_note": ""}
                            for row in approvals
                        ],
                        getRowId="params.data.id",
                        columnDefs=[
                            {"field": "email", "headerName": "Email", "minWidth": 220},
                            {
                                "field": "requested_at",
                                "headerName": "Requested At",
                                "minWidth": 200,
                            },
                            {
                                "field": "grant_role",
                                "headerName": "Grant Role",
                                "cellRenderer": "WorkspaceRequestRole",
                                "cellRendererParams": {
                                    "roles": [
                                        {"label": role.title(), "value": role}
                                        for role in roles
                                    ]
                                },
                                "minWidth": 150,
                                "sortable": False,
                                "filter": False,
                            },
                            {
                                "field": "decision_note",
                                "headerName": "Decision Note (Optional)",
                                "editable": True,
                                "minWidth": 200,
                            },
                            {
                                "headerName": "Decision",
                                "cellRenderer": "WorkspaceRequestDecision",
                                "minWidth": 160,
                                "sortable": False,
                                "filter": False,
                            },
                        ],
                        dashGridOptions={
                            "theme": "themeBalham",
                            "animateRows": True,
                            "pagination": True,
                            "paginationPageSize": 10,
                            "paginationPageSizeSelector": False,
                            "rowHeight": 52,
                            "overlayNoRowsTemplate": "No verified users awaiting approval.",
                        },
                        columnSize="responsiveSizeToFit",
                        defaultColDef={"filter": True, "sortable": True},
                        className="ag-theme-balham admin-request-grid",
                    ),
                ],
                wide=True,
            )
        )
        code = data.get("registration_code")
        if code:
            children.append(
                panel(
                    "Workspace Registration",
                    "Share this link with people who need workspace access.",
                    [
                        field(
                            "Registration Link",
                            dbc.Input(
                                value=current_app.config["AUTH_APP_ORIGIN"]
                                + "/signup?workspace="
                                + code,
                                readonly=True,
                                id="workspace-admin-registration-link",
                            ),
                        ),
                        html.P(
                            "Registration and email verification add a request to the queue; approval is still required.",
                            className="admin-caption",
                        ),
                    ],
                    wide=True,
                )
            )
        children.append(
            panel(
                "Members",
                "Update a member’s role or workspace access.",
                [
                    field(
                        "Select Member",
                        dcc.Dropdown(
                            id="workspace-admin-member",
                            options=[
                                {
                                    "label": f"{m['email']} · {m['role'].title()} · {'Active' if m['active'] else 'Revoked'}",
                                    "value": m["user_id"],
                                }
                                for m in manageable
                            ],
                            placeholder="Choose a member",
                        ),
                    ),
                    html.Div(
                        [
                            role_field(
                                "Assigned Role", "workspace-admin-member-role", roles
                            ),
                            field(
                                "Access Status",
                                dcc.Dropdown(
                                    id="workspace-admin-member-active",
                                    options=[
                                        {"label": "Active", "value": "active"},
                                        {"label": "Revoked", "value": "revoked"},
                                    ],
                                    value="active",
                                    clearable=False,
                                ),
                            ),
                        ],
                        className="admin-form-row",
                    ),
                    html.P(
                        (
                            "No members available in this batch."
                            if not manageable
                            else (
                                "Admins can manage Viewers only."
                                if w["role"] == "admin"
                                else "At least one active Owner must remain."
                            )
                        ),
                        className="admin-caption",
                    ),
                    html.Div(
                        button("Update Member", "workspace-admin-change"),
                        className="admin-panel-actions",
                    ),
                ],
                wide=True,
            )
        )
        children.append(
            panel(
                "Recent Governance Activity",
                "A record of workspace and access changes.",
                [
                    (
                        html.Ul(
                            [activity_item(event) for event in data["events"]],
                            className="admin-activity-list",
                        )
                        if data["events"]
                        else html.P(
                            "No governance activity yet.", className="admin-empty"
                        )
                    ),
                ],
                wide=True,
            )
        )
        if g.workspace_context.get("platform_admin"):
            children.append(
                dbc.Accordion(
                    [
                        dbc.AccordionItem(
                            [
                                html.P(
                                    "Create a separate workspace with its own membership. All workspaces share the AdventureWorks analytics dataset.",
                                    className="muted",
                                ),
                                html.Div(
                                    [
                                        text_field(
                                            "Workspace Name", "workspace-admin-new-name"
                                        ),
                                        text_field(
                                            "Responsible Team",
                                            "workspace-admin-new-team",
                                        ),
                                    ],
                                    className="admin-form-row",
                                ),
                                text_field(
                                    "Purpose", "workspace-admin-new-purpose", "", 1000
                                ),
                                text_field(
                                    "Confirmed Owner Email",
                                    "workspace-admin-new-owner",
                                    "",
                                    254,
                                ),
                                button("Create Workspace", "workspace-admin-create"),
                            ],
                            title="Create Workspace · Platform Administration",
                        ),
                    ],
                    start_collapsed=True,
                    className="admin-provisioning admin-wide",
                )
            )
        count = max(data["member_count"], data["approval_count"])
        if count > 50 or offset:
            children.append(
                html.Nav(
                    [
                        dbc.Button(
                            "Previous",
                            id="workspace-admin-previous",
                            n_clicks=0,
                            disabled=offset == 0,
                            color=None,
                            className="button",
                        ),
                        html.Span(f"Page {offset // 50 + 1}", className="muted"),
                        dbc.Button(
                            "Next",
                            id="workspace-admin-next",
                            n_clicks=0,
                            disabled=offset + 50 >= count,
                            color=None,
                            className="button",
                        ),
                    ],
                    className="admin-pagination admin-wide",
                    **{"aria-label": "Member and approval pages"},
                )
            )
        return html.Div(children, className="workspace-admin-grid")
    except (GovernanceError, ValueError) as error:
        if isinstance(error, GovernanceError) and error.status in (401, 403, 503):
            abort(error.status)
        return dbc.Alert(str(error), color="danger")


@callback(
    Output("workspace-admin-edit-modal", "is_open"),
    Input("workspace-admin-edit", "n_clicks", allow_optional=True),
    Input("workspace-admin-edit-cancel", "n_clicks", allow_optional=True),
    prevent_initial_call=True,
)
def toggle_details_editor(edit_clicks, cancel_clicks):
    w = require_admin()
    if w["role"] not in ("owner", "platform_admin"):
        abort(403)
    if ctx.triggered_id == "workspace-admin-edit" and edit_clicks:
        return True
    if ctx.triggered_id == "workspace-admin-edit-cancel" and cancel_clicks:
        return False
    raise PreventUpdate


@callback(
    Output("workspace-admin-page-offset", "data"),
    Input("workspace-admin-previous", "n_clicks", allow_optional=True),
    Input("workspace-admin-next", "n_clicks", allow_optional=True),
    State("workspace-admin-page-offset", "data"),
    prevent_initial_call=True,
)
def page_lists(previous, next_clicks, offset):
    require_admin()
    if ctx.triggered_id == "workspace-admin-previous" and previous:
        return max(0, int(offset or 0) - 50)
    if ctx.triggered_id == "workspace-admin-next" and next_clicks:
        return int(offset or 0) + 50
    raise PreventUpdate


@callback(
    Output("workspace-admin-requests", "dashGridOptions"),
    Input("workspace-admin-request-search", "value"),
    prevent_initial_call=True,
)
def search_access_requests(value):
    from dash import Patch

    require_admin()
    result = Patch()
    result["quickFilterText"] = value or ""
    return result


ACTION_INPUTS = [
    "save",
    "create",
    "change",
]
STATE_FIELDS = [
    "name",
    "team",
    "purpose",
    "new-name",
    "new-team",
    "new-purpose",
    "new-owner",
    "member",
    "member-role",
    "member-active",
]


@callback(
    Output("workspace-admin-status", "children"),
    Output("workspace-admin-reload", "href"),
    *[
        Input("workspace-admin-" + key, "n_clicks", allow_optional=True)
        for key in ACTION_INPUTS
    ],
    *[
        State("workspace-admin-" + key, "value", allow_optional=True)
        for key in STATE_FIELDS
    ],
    prevent_initial_call=True,
)
def mutate(*args):
    if not ctx.triggered_id or not any(args[: len(ACTION_INPUTS)]):
        raise PreventUpdate
    values = dict(zip(STATE_FIELDS, args[len(ACTION_INPUTS) :]))
    try:
        w = require_admin()
        action = ctx.triggered_id.removeprefix("workspace-admin-")
        if action == "create":
            if not g.workspace_context.get("platform_admin"):
                raise GovernanceError("Platform administrator required.", 403)
            new_id = g.governance.rpc(
                "create_workspace",
                p_name=values["new-name"],
                p_team=values["new-team"],
                p_purpose=values["new-purpose"],
                p_owner_email=values["new-owner"],
            )
            session["workspace_id"] = new_id
        elif action == "save":
            g.governance.rpc(
                "update_workspace",
                p_workspace=w["id"],
                p_name=values["name"],
                p_team=values["team"],
                p_purpose=values["purpose"],
            )
        elif action == "change":
            if not values["member"] or values["member-active"] not in (
                "active",
                "revoked",
            ):
                raise GovernanceError("Choose a member, role, and status.", 400)
            g.governance.rpc(
                "change_workspace_member",
                p_workspace=w["id"],
                p_user=values["member"],
                p_role=values["member-role"],
                p_active=values["member-active"] == "active",
            )
        else:
            raise PreventUpdate
        return (
            dbc.Alert(
                "Change saved. Reloading workspace permissions…", color="success"
            ),
            "/workspace/admin",
        )
    except GovernanceError as error:
        if error.status in (401, 403, 503):
            abort(error.status)
        return dbc.Alert(str(error), color="danger"), dash.no_update


@callback(
    Output("workspace-admin-member-role", "value"),
    Output("workspace-admin-member-active", "value"),
    Input("workspace-admin-member", "value"),
    State("workspace-admin-page-offset", "data"),
    prevent_initial_call=True,
)
def selected_member(user_id, offset):
    if not user_id:
        raise PreventUpdate
    try:
        w = require_admin()
        data = g.governance.rpc(
            "workspace_admin_data", p_workspace=w["id"], p_offset=int(offset or 0)
        )
        member = next((m for m in data["members"] if m["user_id"] == user_id), None)
        if not member or (w["role"] == "admin" and member["role"] != "viewer"):
            raise PreventUpdate
        return member["role"], "active" if member["active"] else "revoked"
    except GovernanceError as error:
        if error.status in (401, 403, 503):
            abort(error.status)
        raise PreventUpdate


@callback(
    Output("workspace-admin-status", "children", allow_duplicate=True),
    Output("workspace-admin-reload", "href", allow_duplicate=True),
    Input("workspace-admin-requests", "cellRendererData"),
    prevent_initial_call=True,
)
def review_request_row(event):
    if not event:
        raise PreventUpdate
    w = require_admin()
    values = event.get("value")
    if not isinstance(values, dict):
        raise PreventUpdate
    try:
        decision, role = values.get("decision"), values.get("role")
        reason = values.get("reason", "")
        if (
            not isinstance(values.get("request_id"), str)
            or not values["request_id"]
            or decision not in ("approved", "rejected")
            or role not in ("viewer", "admin", "owner")
            or not isinstance(reason, str)
            or len(reason) > 1000
        ):
            raise GovernanceError("Choose a valid request, role, and decision.", 400)
        if w["role"] == "admin" and role != "viewer":
            raise GovernanceError("Admins can manage Viewers only.", 403)
        g.governance.rpc(
            "review_workspace_request",
            p_workspace=w["id"],
            p_request=values["request_id"],
            p_decision=decision,
            p_role=role,
            p_reason=reason,
        )
        return (
            dbc.Alert(
                "Request " + decision + ". Reloading the approval queue…",
                color="success",
            ),
            "/workspace/admin",
        )
    except GovernanceError as error:
        if error.status in (401, 403, 503):
            abort(error.status)
        return dbc.Alert(str(error), color="danger"), dash.no_update
