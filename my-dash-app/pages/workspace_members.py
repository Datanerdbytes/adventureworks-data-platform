"""Workspace-filtered administrative member directory; writes stay in checked RPCs."""

from datetime import datetime, timezone
from urllib.parse import parse_qs
from uuid import UUID, uuid4

import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask import abort, g
from components import field, heading
from governance import GovernanceError

PATH = "/workspace/admin/members"
ALL = "__all__"
PAGE_SIZE = 10
ADMIN_ROLES = {"owner", "admin", "platform_admin"}
dash.register_page(__name__, path=PATH, title="Members | AdventureWorks")


def managed_workspaces():
    workspaces = [
        w for w in g.workspace_context.get("workspaces", []) if w["role"] in ADMIN_ROLES
    ]
    if not workspaces:
        abort(403)
    return {w["id"]: w for w in workspaces}


def resolve_scope(scope):
    workspaces = managed_workspaces()
    if scope == ALL:
        return None
    if scope not in workspaces:
        abort(403)
    return scope


def timestamp(value):
    try:
        return (
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .strftime("%d %b %Y · %H:%M UTC")
        )
    except (AttributeError, TypeError, ValueError):
        return "Unavailable"


def layout(**_query):
    # Dash Pages passes URL query parameters here; load_scopes validates scope.
    return html.Div(
        [
            heading(
                "Members",
                "Find people, review membership details, and manage workspace access.",
                dcc.Link(
                    "← Workspace Admin", href="/workspace/admin", className="button"
                ),
            ),
            html.Div(
                id="workspace-members-status", role="status", **{"aria-live": "polite"}
            ),
            dbc.Card(
                [
                    html.Div(
                        [
                            field(
                                "Workspace",
                                dcc.Dropdown(
                                    id="workspace-members-scope",
                                    options=[],
                                    clearable=False,
                                ),
                            ),
                            field(
                                "Search email",
                                dbc.Input(
                                    id="workspace-members-search",
                                    type="search",
                                    value="",
                                    maxLength=200,
                                    autoComplete="off",
                                    debounce=True,
                                    placeholder="Find a member by email",
                                ),
                            ),
                            field(
                                "Role",
                                dcc.Dropdown(
                                    id="workspace-members-role",
                                    options=[{"label": "All roles", "value": ALL}]
                                    + [
                                        {"label": r.title(), "value": r}
                                        for r in ("owner", "admin", "viewer")
                                    ],
                                    value=ALL,
                                    clearable=False,
                                ),
                            ),
                            field(
                                "Access",
                                dcc.Dropdown(
                                    id="workspace-members-active",
                                    options=[
                                        {"label": "All statuses", "value": ALL},
                                        {"label": "Active", "value": "active"},
                                        {"label": "Revoked", "value": "revoked"},
                                    ],
                                    value=ALL,
                                    clearable=False,
                                ),
                            ),
                        ],
                        className="admin-directory-filters",
                    ),
                    html.Div(
                        [
                            html.P(
                                id="workspace-members-summary",
                                role="status",
                                **{"aria-live": "polite"},
                            ),
                            dbc.Button(
                                "View member details",
                                id="workspace-members-view",
                                n_clicks=0,
                                disabled=True,
                                color=None,
                                className="button",
                            ),
                        ],
                        className="admin-directory-toolbar",
                    ),
                    html.P(
                        "Select a member to view their details or update access. Filters search all matching memberships.",
                        className="admin-caption",
                    ),
                    html.Div(id="workspace-members-error", role="alert"),
                    dcc.Loading(
                        dag.AgGrid(
                            id="workspace-members-grid",
                            rowData=[],
                            columnDefs=[
                                {**column, "filter": False, "sortable": False}
                                for column in [
                                    {
                                        "field": "email",
                                        "headerName": "Member email",
                                        "minWidth": 230,
                                    },
                                    {
                                        "field": "workspace_name",
                                        "headerName": "Workspace",
                                        "minWidth": 180,
                                    },
                                    {
                                        "field": "role_label",
                                        "headerName": "Role",
                                        "minWidth": 110,
                                    },
                                    {
                                        "field": "status",
                                        "headerName": "Access",
                                        "minWidth": 110,
                                    },
                                    {
                                        "field": "joined",
                                        "headerName": "Joined (UTC)",
                                        "minWidth": 200,
                                    },
                                ]
                            ],
                            # Directory filters and pagination run server-side. Disable
                            # page-local sorting/filtering to avoid misleading global results.
                            defaultColDef={"filter": True, "sortable": True},
                            dashGridOptions={
                                "theme": "themeBalham",
                                "animateRows": True,
                                "pagination": True,
                                "paginationPageSize": 10,
                                "suppressPaginationPanel": True,
                                "domLayout": "autoHeight",
                                "rowHeight": 48,
                                "headerHeight": 44,
                                "rowSelection": {
                                    "mode": "singleRow",
                                    "enableClickSelection": True,
                                },
                                "overlayNoRowsTemplate": "No members match these filters.",
                            },
                            getRowId="params.data.workspace_id + ':' + params.data.user_id",
                            columnSize="responsiveSizeToFit",
                            className="ag-theme-balham admin-member-grid",
                        ),
                        type="circle",
                    ),
                    html.Nav(
                        [
                            html.Span(
                                id="workspace-members-page-label", className="muted"
                            ),
                            html.Div(
                                [
                                    dbc.Button(
                                        "Previous",
                                        id="workspace-members-previous",
                                        n_clicks=0,
                                        color=None,
                                        className="button",
                                        disabled=True,
                                    ),
                                    dbc.Button(
                                        "Next",
                                        id="workspace-members-next",
                                        n_clicks=0,
                                        color=None,
                                        className="button",
                                        disabled=True,
                                    ),
                                ]
                            ),
                        ],
                        className="admin-compact-pagination",
                        **{"aria-label": "Member directory pages"},
                    ),
                ],
                className="admin-panel admin-directory-panel",
            ),
            dcc.Store(id="workspace-members-page", data={"offset": 0, "total": 0}),
            dcc.Store(id="workspace-members-target"),
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle("Member details")),
                    dbc.ModalBody(
                        [
                            html.Div(id="workspace-members-details"),
                            html.Div(id="workspace-members-edit-status", role="alert"),
                        ]
                    ),
                    dbc.ModalFooter(
                        [
                            dbc.Button(
                                "Cancel",
                                id="workspace-members-cancel",
                                n_clicks=0,
                                color=None,
                                className="button",
                            ),
                            dbc.Button(
                                "Save changes",
                                id="workspace-members-save",
                                n_clicks=0,
                                color=None,
                                className="button primary",
                            ),
                        ]
                    ),
                ],
                id="workspace-members-modal",
                is_open=False,
                centered=True,
                className="workspace-admin-page admin-edit-modal admin-member-modal",
                backdrop_class_name="admin-edit-backdrop",
                fade=False,
            ),
            dcc.Store(id="workspace-members-refresh"),
        ],
        className="workspace-admin-page workspace-members-page",
    )


@callback(
    Output("workspace-members-scope", "options"),
    Output("workspace-members-scope", "value"),
    Input("app-location", "pathname"),
    State("app-location", "search"),
)
def load_scopes(path, search):
    if path != PATH:
        raise PreventUpdate
    allowed = managed_workspaces()
    requested = parse_qs((search or "").lstrip("?")).get("workspace", [None])[0]
    if requested and requested not in allowed and requested != ALL:
        abort(403)
    selected = requested or (
        g.workspace["id"] if g.workspace["id"] in allowed else next(iter(allowed))
    )
    return [{"label": "All managed workspaces", "value": ALL}] + [
        {"label": w["name"], "value": w["id"]} for w in allowed.values()
    ], selected


@callback(
    Output("workspace-members-grid", "rowData"),
    Output("workspace-members-grid", "selectedRows"),
    Output("workspace-members-summary", "children"),
    Output("workspace-members-page-label", "children"),
    Output("workspace-members-previous", "disabled"),
    Output("workspace-members-next", "disabled"),
    Output("workspace-members-page", "data"),
    Output("workspace-members-error", "children"),
    Input("app-location", "pathname"),
    Input("workspace-members-scope", "value"),
    Input("workspace-members-search", "value"),
    Input("workspace-members-role", "value"),
    Input("workspace-members-active", "value"),
    Input("workspace-members-previous", "n_clicks"),
    Input("workspace-members-next", "n_clicks"),
    Input("workspace-members-refresh", "data"),
    State("workspace-members-page", "data"),
)
def load_members(
    path, scope, query, role, active, previous, next_clicks, refresh, page
):
    if path != PATH or scope is None:
        raise PreventUpdate
    target = resolve_scope(scope)
    if role not in (ALL, "owner", "admin", "viewer") or active not in (
        ALL,
        "active",
        "revoked",
    ):
        abort(400)
    query = query or ""
    if not isinstance(query, str) or len(query) > 200:
        abort(400)
    offset = 0
    if ctx.triggered_id in (
        "workspace-members-previous",
        "workspace-members-next",
        "workspace-members-refresh",
    ):
        try:
            offset = int((page or {}).get("offset", 0))
        except (ValueError, TypeError):
            abort(400)
        if ctx.triggered_id != "workspace-members-refresh":
            offset += (
                PAGE_SIZE
                if ctx.triggered_id == "workspace-members-next"
                else -PAGE_SIZE
            )
        offset = max(0, min(offset, 100000))
    try:
        data = g.governance.rpc(
            "workspace_members_directory",
            p_workspace=target,
            p_offset=offset,
            p_query=query.strip(),
            p_role=None if role == ALL else role,
            p_active=None if active == ALL else active == "active",
        )
        if data["offset"] and data["offset"] >= data["total"]:
            data = g.governance.rpc(
                "workspace_members_directory",
                p_workspace=target,
                p_offset=max(0, ((data["total"] - 1) // PAGE_SIZE) * PAGE_SIZE),
                p_query=query.strip(),
                p_role=None if role == ALL else role,
                p_active=None if active == ALL else active == "active",
            )
        members, total, offset = data["members"], data["total"], data["offset"]
        rows = [
            {
                **m,
                "role_label": m["role"].title(),
                "status": "Active" if m["active"] else "Revoked",
                "joined": timestamp(m.get("created_at")),
            }
            for m in members
        ]
        return (
            rows,
            [],
            f"{total} matching membership{'s' if total != 1 else ''}",
            f"{offset + 1}–{offset + len(rows)} of {total}" if total else "0 members",
            offset == 0,
            offset + PAGE_SIZE >= total or offset >= 100000,
            {"offset": offset, "total": total},
            "",
        )
    except GovernanceError as error:
        if error.status in (401, 403):
            abort(error.status)
        return (
            [],
            [],
            "Members unavailable",
            "",
            True,
            True,
            {"offset": 0, "total": 0},
            dbc.Alert("Unable to load members. Reload to retry.", color="danger"),
        )


@callback(
    Output("workspace-members-view", "disabled"),
    Input("workspace-members-grid", "selectedRows"),
)
def can_view_selection(rows):
    managed_workspaces()
    return not bool(rows and len(rows) == 1)


def selected_member(target, scope):
    allowed = managed_workspaces()
    resolve_scope(scope)
    if not isinstance(target, dict) or target.get("workspace_id") not in allowed:
        abort(403)
    workspace_id = target["workspace_id"]
    if scope != ALL and scope != workspace_id:
        abort(403)
    try:
        user_id = str(UUID(target.get("user_id", "")))
    except (ValueError, TypeError, AttributeError):
        abort(400)
    # Refetch canonical details and current role before displaying or changing
    # access. A selectedRows payload is editable client state, not authority.
    data = g.governance.rpc(
        "workspace_members_directory",
        p_workspace=workspace_id,
        p_user=user_id,
        p_offset=0,
    )
    member = next(
        (
            m
            for m in data["members"]
            if m["user_id"] == user_id and m["workspace_id"] == workspace_id
        ),
        None,
    )
    if member is None:
        raise GovernanceError("Member not found", 400)
    return member, allowed[workspace_id]["role"]


@callback(
    Output("workspace-members-modal", "is_open"),
    Output("workspace-members-details", "children"),
    Output("workspace-members-target", "data"),
    Output("workspace-members-save", "disabled"),
    Output("workspace-members-edit-status", "children"),
    Input("workspace-members-view", "n_clicks"),
    Input("workspace-members-cancel", "n_clicks"),
    State("workspace-members-grid", "selectedRows"),
    State("workspace-members-scope", "value"),
    prevent_initial_call=True,
)
def open_member(view, cancel, rows, scope):
    managed_workspaces()
    if ctx.triggered_id == "workspace-members-cancel":
        return False, no_update, None, True, ""
    if not view or not rows or len(rows) != 1:
        raise PreventUpdate
    try:
        member, actor_role = selected_member(rows[0], scope)
        can_edit = actor_role != "admin" or (
            member["role"] == "viewer" and member["user_id"] != g.auth_user["id"]
        )
        roles = ["viewer"] if actor_role == "admin" else ["viewer", "admin", "owner"]
        details = html.Div(
            [
                html.H3(member["email"], className="admin-member-email"),
                html.Dl(
                    [
                        html.Div([html.Dt(label), html.Dd(value)])
                        for label, value in [
                            ("Workspace", member["workspace_name"]),
                            (
                                "Email verification",
                                (
                                    "Verified"
                                    if member.get("email_confirmed")
                                    else "Unverified"
                                ),
                            ),
                            ("Joined", timestamp(member.get("created_at"))),
                            ("Last updated", timestamp(member.get("updated_at"))),
                            ("User ID", member["user_id"]),
                        ]
                    ],
                    className="admin-member-details",
                ),
                html.Div(
                    [
                        field(
                            "Assigned role",
                            dcc.Dropdown(
                                id="workspace-members-edit-role",
                                options=[
                                    {"label": r.title(), "value": r}
                                    for r in (roles if can_edit else [member["role"]])
                                ],
                                value=member["role"],
                                clearable=False,
                                disabled=not can_edit,
                            ),
                        ),
                        field(
                            "Access status",
                            dcc.Dropdown(
                                id="workspace-members-edit-active",
                                options=[
                                    {"label": "Active", "value": "active"},
                                    {"label": "Revoked", "value": "revoked"},
                                ],
                                value="active" if member["active"] else "revoked",
                                clearable=False,
                                disabled=not can_edit,
                            ),
                        ),
                    ],
                    className="admin-form-row",
                ),
                html.P(
                    (
                        "Admins can update other Viewers only."
                        if actor_role == "admin"
                        else "At least one active Owner must remain in each workspace."
                    ),
                    className="admin-caption",
                ),
            ]
        )
        return (
            True,
            details,
            {"workspace_id": member["workspace_id"], "user_id": member["user_id"]},
            not can_edit,
            "",
        )
    except GovernanceError as error:
        if error.status in (401, 403, 503):
            abort(error.status)
        return True, html.P(str(error)), None, True, ""


@callback(
    Output("workspace-members-edit-status", "children", allow_duplicate=True),
    Output("workspace-members-modal", "is_open", allow_duplicate=True),
    Output("workspace-members-target", "data", allow_duplicate=True),
    Output("workspace-members-refresh", "data"),
    Output("workspace-members-status", "children"),
    Output("app-location", "href"),
    Input("workspace-members-save", "n_clicks"),
    State("workspace-members-target", "data"),
    State("workspace-members-edit-role", "value", allow_optional=True),
    State("workspace-members-edit-active", "value", allow_optional=True),
    State("workspace-members-scope", "value"),
    prevent_initial_call=True,
    running=[(Output("workspace-members-save", "disabled"), True, False)],
)
def update_member(clicks, target, role, active, scope):
    if not clicks:
        raise PreventUpdate
    try:
        member, actor_role = selected_member(target, scope)
        if role not in ("owner", "admin", "viewer") or active not in (
            "active",
            "revoked",
        ):
            raise GovernanceError("Choose a valid role and access status.", 400)
        if actor_role == "admin" and (
            member["role"] != "viewer"
            or role != "viewer"
            or member["user_id"] == g.auth_user["id"]
        ):
            abort(403)
        g.governance.rpc(
            "change_workspace_member",
            p_workspace=member["workspace_id"],
            p_user=member["user_id"],
            p_role=role,
            p_active=active == "active",
        )
        own_current_access = (
            member["user_id"] == g.auth_user["id"]
            and member["workspace_id"] == g.workspace["id"]
        )
        return (
            "",
            False,
            None,
            no_update if own_current_access else str(uuid4()),
            dbc.Alert("Member updated.", color="success"),
            "/workspace" if own_current_access else no_update,
        )
    except GovernanceError as error:
        if error.status in (401, 403, 503):
            abort(error.status)
        return (dbc.Alert(str(error), color="danger"), *([no_update] * 5))
