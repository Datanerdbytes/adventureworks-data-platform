"""Admin-only user directory. Layouts are query-free; data stays server scoped."""

import dash
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
from dash import (
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
)
from dash.exceptions import PreventUpdate
from flask import g, has_request_context
from user_admin import (
    AdminError,
    delete_account,
    deletion_target,
    is_admin,
    list_users,
    require_admin,
    require_owner,
    update_access,
)

dash.register_page(__name__, path="/admin/users", name="User management")

ACTIONS = {
    "suspend": (
        "Suspend access",
        "This user will lose workspace access, including existing sessions. Their account and data will be retained.",
    ),
    "restore": (
        "Restore access",
        "This user will be able to sign in again once their email is verified.",
    ),
    "grant_admin": (
        "Grant admin access",
        "This user will be able to view all accounts and change other users’ access and administrator roles.",
    ),
    "revoke_admin": (
        "Revoke admin access",
        "This user will keep access to the analytics workspace but can no longer manage users.",
    ),
}


def layout():
    if has_request_context() and not is_admin(getattr(g, "auth_user", {})):
        return html.Section(
            [
                html.H2("Admin access required"),
                html.P("Only administrators can manage users."),
                html.A("Return to dashboard", href="/dashboard"),
            ]
        )
    grid = dag.AgGrid(
        columnDefs=[
            {
                "field": "email",
                "headerName": "Email address",
                "minWidth": 250,
                "checkboxSelection": True,
                "headerCheckboxSelection": False,
                "flex": 2,
            },
            {"field": "role", "headerName": "Role", "minWidth": 110},
            {"field": "verification", "headerName": "Email", "minWidth": 120},
            {"field": "access", "headerName": "Access", "minWidth": 120},
            {"field": "created_at", "headerName": "Created (UTC)", "minWidth": 200},
            {
                "field": "last_sign_in_at",
                "headerName": "Last sign-in (UTC)",
                "minWidth": 200,
            },
        ],
        id="admin-users-grid",
        className="ag-theme-balham admin-users-grid",
        rowData=[],
        columnSize="responsiveSizeToFit",
        defaultColDef={"filter": True, "sortable": True},
        dashGridOptions={
            "theme": "themeBalham",
            "animateRows": True,
            "pagination": True,
            "paginationPageSize": 10,
            "rowSelection": "single",
            "rowHeight": 48,
            "headerHeight": 44,
            "suppressRowClickSelection": False,
        },
    )
    return html.Section(
        [
            dcc.Location(id="admin-users-location", refresh=False),
            dcc.Store(id="admin-users-page", data=1),
            dcc.Store(id="admin-users-pending-action"),
            dcc.Store(id="admin-users-revision", data=0),
            html.Div(
                id="admin-users-action-message",
                className="admin-action-feedback",
                role="status",
                tabIndex=-1,
                **{"aria-live": "polite", "aria-atomic": "true"},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.P(
                                "WORKSPACE / ACCESS CONTROL", className="admin-eyebrow"
                            ),
                            html.H2("User Management", className="admin-title"),
                            html.P(
                                "Manage sign-in access and administrator roles.",
                                className="admin-intro",
                            ),
                        ]
                    ),
                    html.Span(
                        [
                            html.I(
                                className="account-shield", **{"aria-hidden": "true"}
                            ),
                            "Administrator workspace",
                        ],
                        className="admin-access-badge",
                    ),
                ],
                className="admin-hero",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("01 / DIRECTORY", className="admin-eyebrow"),
                            html.H3("Workspace members"),
                            html.P(
                                "Select one account to review and manage access. Column filters apply to the current directory page."
                            ),
                        ]
                    ),
                    dbc.Button(
                        [
                            html.I(
                                className="account-refresh",
                                **{"aria-hidden": "true"},
                            ),
                            " Refresh directory",
                        ],
                        id="admin-users-refresh",
                        outline=True,
                        color="secondary",
                    ),
                ],
                className="admin-directory-heading",
            ),
            html.Div(
                id="admin-users-load-message", role="status", **{"aria-live": "polite"}
            ),
            dcc.Loading(grid, id="admin-users-grid-loading", type="circle"),
            html.Div(
                [
                    html.Span("Loading directory…", id="admin-users-page-label"),
                    html.Div(
                        [
                            dbc.Button(
                                "Previous accounts",
                                id="admin-users-previous",
                                disabled=True,
                                outline=True,
                                color="secondary",
                            ),
                            dbc.Button(
                                "Next accounts",
                                id="admin-users-next",
                                disabled=True,
                                outline=True,
                                color="secondary",
                            ),
                        ],
                        className="admin-page-buttons",
                    ),
                ],
                className="admin-pagination",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.P("02 / ACCOUNT ACCESS", className="admin-eyebrow"),
                            html.H3("Select an account", id="admin-users-selected"),
                            html.P(
                                "Verification is required for sign-in. Suspension preserves the account and blocks workspace access.",
                                className="admin-intro",
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            dbc.Button(
                                label,
                                id=f"admin-users-{action}",
                                disabled=True,
                                outline=True,
                                color=(
                                    "danger"
                                    if action in ("suspend", "revoke_admin")
                                    else "primary"
                                ),
                            )
                            for action, (label, _) in ACTIONS.items()
                        ],
                        className="admin-account-actions",
                    ),
                    html.P(
                        "The owner and your own account are protected. Only verified, active accounts can become admins. Revoke admin access before suspension.",
                        className="admin-policy-note",
                    ),
                ],
                className="admin-account-panel",
            ),
            html.Section(
                [
                    html.P("03 / PERMANENT REMOVAL", className="admin-eyebrow"),
                    html.H3("Delete account"),
                    html.P(
                        "Owner only. Select a suspended member to permanently remove their sign-in account. Revoke administrator access first. A deleted email address can register again.",
                        className="admin-intro",
                    ),
                    dbc.Button(
                        "Delete account",
                        id="admin-users-delete",
                        color="danger",
                        outline=True,
                        disabled=True,
                    ),
                ],
                id="admin-users-delete-section",
                className="admin-account-panel admin-delete-panel",
                hidden=not (
                    has_request_context()
                    and (getattr(g, "auth_user", {}).get("app_metadata") or {}).get(
                        "qe_owner"
                    )
                    is True
                ),
            ),
            dcc.Store(id="admin-users-delete-pending"),
            dcc.Store(id="admin-users-delete-busy", data=False),
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle("Permanently delete account?")),
                    dbc.ModalBody(
                        [
                            html.P(
                                id="admin-users-delete-email",
                                className="admin-confirm-email",
                            ),
                            html.P(
                                "This permanently deletes the Supabase sign-in account. Linked records configured to cascade on account deletion may also be removed. This cannot be undone."
                            ),
                            html.Label(
                                "Type the account’s full email address to confirm",
                                htmlFor="admin-users-delete-confirmation",
                            ),
                            dcc.Input(
                                id="admin-users-delete-confirmation",
                                type="text",
                                autoComplete="off",
                                maxLength=320,
                                className="admin-delete-confirmation",
                            ),
                            html.Div(
                                id="admin-users-delete-error",
                                role="alert",
                                className="admin-delete-error",
                            ),
                        ]
                    ),
                    dbc.ModalFooter(
                        [
                            dbc.Button(
                                "Cancel",
                                id="admin-users-delete-cancel",
                                color="secondary",
                                outline=True,
                            ),
                            dbc.Button(
                                "Permanently delete account",
                                id="admin-users-delete-confirm",
                                color="danger",
                                disabled=True,
                            ),
                        ]
                    ),
                ],
                id="admin-users-delete-modal",
                is_open=False,
                centered=True,
                className="admin-edit-modal admin-account-modal",
                backdrop_class_name="admin-edit-backdrop",
                backdrop="static",
            ),
            dbc.Modal(
                [
                    dbc.ModalHeader(
                        dbc.ModalTitle(
                            "Confirm access change", id="admin-users-confirm-title"
                        )
                    ),
                    dbc.ModalBody(
                        [
                            html.P(
                                id="admin-users-confirm-email",
                                className="admin-confirm-email",
                            ),
                            html.P(id="admin-users-confirm-description"),
                        ]
                    ),
                    dbc.ModalFooter(
                        [
                            dbc.Button(
                                "Cancel",
                                id="admin-users-cancel",
                                color="secondary",
                                outline=True,
                            ),
                            dbc.Button(
                                "Confirm change",
                                id="admin-users-confirm",
                                color="primary",
                            ),
                        ]
                    ),
                ],
                id="admin-users-confirm-modal",
                is_open=False,
                centered=True,
                className="admin-edit-modal admin-account-modal",
                backdrop_class_name="admin-edit-backdrop",
            ),
        ],
        className="admin-users-page",
    )


@callback(
    Output("admin-users-page", "data"),
    Input("admin-users-previous", "n_clicks"),
    Input("admin-users-next", "n_clicks"),
    State("admin-users-page", "data"),
    prevent_initial_call=True,
)
def change_page(_previous, _next, page):
    require_admin()
    page = page if isinstance(page, int) and not isinstance(page, bool) else 1
    return max(
        1, min(100_000, page + (1 if ctx.triggered_id == "admin-users-next" else -1))
    )


@callback(
    Output("admin-users-grid", "rowData"),
    Output("admin-users-grid", "selectedRows"),
    Output("admin-users-load-message", "children"),
    Output("admin-users-page-label", "children"),
    Output("admin-users-previous", "disabled"),
    Output("admin-users-next", "disabled"),
    Input("admin-users-location", "pathname"),
    Input("admin-users-page", "data"),
    Input("admin-users-refresh", "n_clicks"),
    Input("admin-users-revision", "data"),
)
def load_directory(pathname, page, _refresh, _revision):
    if pathname != "/admin/users":
        raise PreventUpdate
    try:
        data = list_users(page)
    except AdminError as error:
        return (
            [],
            [],
            dbc.Alert(str(error), color="warning"),
            "Directory unavailable",
            True,
            True,
        )
    rows = data["users"]
    message = "No accounts on this page." if not rows else ""
    return (
        rows,
        [],
        message,
        f"Directory page {page} · {len(rows)} accounts · up to 25 per page",
        page <= 1,
        not data["has_next"],
    )


@callback(
    Output("admin-users-selected", "children"),
    *[Output(f"admin-users-{action}", "disabled") for action in ACTIONS],
    Input("admin-users-grid", "selectedRows"),
)
def selected_account(rows):
    actor = require_admin()
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        return "Select an account", True, True, True, True
    user = rows[0]
    protected = user.get("owner") or user.get("id") == actor["id"]
    suspended = user.get("access") == "Suspended"
    admin = user.get("role") == "Admin"
    return (
        user.get("email", "Selected account"),
        bool(protected or suspended or admin),
        bool(protected or not suspended),
        bool(protected or admin or suspended or user.get("verification") != "Verified"),
        bool(protected or not admin),
    )


@callback(
    Output("admin-users-confirm-modal", "is_open"),
    Output("admin-users-confirm-title", "children"),
    Output("admin-users-confirm-email", "children"),
    Output("admin-users-confirm-description", "children"),
    Output("admin-users-pending-action", "data"),
    Output("admin-users-action-message", "children"),
    Output("admin-users-revision", "data"),
    *[Input(f"admin-users-{action}", "n_clicks") for action in ACTIONS],
    Input("admin-users-cancel", "n_clicks"),
    Input("admin-users-confirm", "n_clicks"),
    State("admin-users-grid", "selectedRows"),
    State("admin-users-pending-action", "data"),
    State("admin-users-revision", "data"),
    prevent_initial_call=True,
    running=[(Output("admin-users-confirm", "disabled"), True, False)],
)
def manage_account(
    _suspend, _restore, _grant, _revoke, _cancel, _confirm, rows, pending, revision
):
    try:
        require_admin()
        trigger = ctx.triggered_id
        if trigger == "admin-users-cancel":
            return False, no_update, no_update, no_update, None, no_update, no_update
        if trigger == "admin-users-confirm":
            if not isinstance(pending, dict):
                raise AdminError("invalid_request", 400)
            message = update_access(pending.get("id"), pending.get("action"))
            revision = (
                revision
                if isinstance(revision, int) and not isinstance(revision, bool)
                else 0
            )
            return (
                False,
                no_update,
                no_update,
                no_update,
                None,
                dbc.Alert(
                    message,
                    color="success",
                    duration=5000,
                    is_open=True,
                    key=f"admin-success-{revision + 1}",
                ),
                revision + 1,
            )
        action = str(trigger).removeprefix("admin-users-")
        if action not in ACTIONS or not isinstance(rows, list) or len(rows) != 1:
            raise AdminError("invalid_request", 400)
        row = rows[0]
        if not isinstance(row, dict):
            raise AdminError("invalid_request", 400)
        title, description = ACTIONS[action]
        # Client state carries only a selected ID/action, never authority.
        return (
            True,
            title,
            row.get("email", "Selected account"),
            description,
            {"id": row.get("id"), "action": action},
            "",
            no_update,
        )
    except AdminError as error:
        return (
            False,
            no_update,
            no_update,
            no_update,
            None,
            dbc.Alert(str(error), color="warning"),
            no_update,
        )


clientside_callback(
    """function(message) {
        if (!message) return window.dash_clientside.no_update;
        const reveal = function() {
            window.requestAnimationFrame(function() {
                const region = document.getElementById('admin-users-action-message');
                if (region) region.scrollIntoView({block: 'start', behavior: 'auto'});
            });
        };
        const dialogOpen = function() { return document.getElementById('admin-users-confirm-modal') || document.getElementById('admin-users-delete-modal'); };
        if (dialogOpen()) {
            // Wait for the closing dialog to restore focus before scrolling.
            const observer = new MutationObserver(function() {
                if (!dialogOpen()) {
                    observer.disconnect();
                    reveal();
                }
            });
            observer.observe(document.body, {childList: true, subtree: true});
        } else {
            reveal();
        }
        return -1;
    }""",
    Output("admin-users-action-message", "tabIndex"),
    Input("admin-users-action-message", "children"),
    prevent_initial_call=True,
)


@callback(
    Output("admin-users-delete", "disabled"),
    Input("admin-users-grid", "selectedRows"),
)
def deletion_available(rows):
    actor = require_admin()
    owner = (actor.get("app_metadata") or {}).get("qe_owner") is True
    if (
        not owner
        or not isinstance(rows, list)
        or len(rows) != 1
        or not isinstance(rows[0], dict)
    ):
        return True
    user = rows[0]
    return bool(
        user.get("owner")
        or user.get("id") == actor["id"]
        or user.get("role") == "Admin"
        or user.get("access") != "Suspended"
    )


@callback(
    Output("admin-users-delete-modal", "is_open"),
    Output("admin-users-delete-pending", "data"),
    Output("admin-users-delete-email", "children"),
    Output("admin-users-delete-confirmation", "value"),
    Output("admin-users-delete-error", "children"),
    Output("admin-users-action-message", "children", allow_duplicate=True),
    Output("admin-users-revision", "data", allow_duplicate=True),
    Input("admin-users-delete", "n_clicks"),
    Input("admin-users-delete-cancel", "n_clicks"),
    Input("admin-users-delete-confirm", "n_clicks"),
    State("admin-users-grid", "selectedRows"),
    State("admin-users-delete-pending", "data"),
    State("admin-users-delete-confirmation", "value"),
    State("admin-users-revision", "data"),
    prevent_initial_call=True,
    running=[(Output("admin-users-delete-busy", "data"), True, False)],
)
def manage_deletion(
    _open, _cancel, _confirm, rows, pending, confirmation_email, revision
):
    try:
        require_owner()
        trigger = ctx.triggered_id
        if trigger == "admin-users-delete-cancel":
            return False, None, "", "", "", no_update, no_update
        if trigger == "admin-users-delete-confirm":
            if not isinstance(pending, dict):
                raise AdminError("invalid_request", 400)
            message = delete_account(pending.get("id"), confirmation_email)
            revision = (
                revision
                if isinstance(revision, int) and not isinstance(revision, bool)
                else 0
            )
            return (
                False,
                None,
                "",
                "",
                "",
                dbc.Alert(
                    message,
                    color="success",
                    duration=5000,
                    is_open=True,
                    key=f"admin-success-{revision + 1}",
                ),
                revision + 1,
            )
        if (
            trigger != "admin-users-delete"
            or not isinstance(rows, list)
            or len(rows) != 1
            or not isinstance(rows[0], dict)
        ):
            raise AdminError("invalid_request", 400)
        target = deletion_target(rows[0].get("id"))
        return (
            True,
            {"id": target["id"], "email": target["email"]},
            target["email"],
            "",
            "",
            "",
            no_update,
        )
    except AdminError as error:
        if error.code == "confirmation_mismatch":
            return (
                True,
                no_update,
                no_update,
                no_update,
                str(error),
                no_update,
                no_update,
            )
        return (
            False,
            None,
            "",
            "",
            "",
            dbc.Alert(str(error), color="warning"),
            no_update,
        )


clientside_callback(
    """function(value, pending, busy) {
        return Boolean(busy || !pending || typeof value !== 'string' || typeof pending.email !== 'string' || value.trim().toLowerCase() !== pending.email.trim().toLowerCase());
    }""",
    Output("admin-users-delete-confirm", "disabled"),
    Input("admin-users-delete-confirmation", "value"),
    Input("admin-users-delete-pending", "data"),
    Input("admin-users-delete-busy", "data"),
)
