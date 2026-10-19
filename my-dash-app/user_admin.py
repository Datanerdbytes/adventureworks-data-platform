"""Server-only Supabase user administration. Never return raw Auth records."""

import json
import os
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from flask import g, has_request_context, jsonify, request

PAGE_SIZE = 25
MESSAGES = {
    "access_guard_required": "Access changes are unavailable until the database safety migration is installed.",
    "admin_required": "Only administrators can manage users.",
    "admin_not_configured": "User management needs a server-side Supabase service-role key.",
    "admin_unavailable": "User management is temporarily unavailable. Please retry.",
    "invalid_request": "Choose a valid user and action.",
    "protected_account": "Administrator accounts cannot be suspended from this page.",
    "owner_protected": "The initial owner account cannot be changed from this page.",
    "self_change": "Use another administrator account to change your own access.",
    "verification_required": "Only verified, active accounts can become administrators.",
    "owner_required": "Only the protected owner can delete accounts.",
    "suspension_required": "Suspend this account before deleting it.",
    "admin_deletion_protected": "Revoke administrator access before deleting this account.",
    "confirmation_mismatch": "Type the selected account’s full email address to confirm deletion.",
    "delete_guard_required": "Account deletion is unavailable until the database safety migration is installed. Contact your administrator.",
    "delete_blocked": "Supabase blocked deletion. Review linked records and Storage ownership before retrying.",
    "delete_unconfirmed": "Deletion could not be confirmed. Refresh the directory before retrying: access may have changed, or linked records and Storage ownership may block removal.",
    "user_not_found": "This account no longer exists. Refresh the directory.",
}


class AdminError(Exception):
    def __init__(self, code, status):
        self.code, self.status = code, status
        super().__init__(MESSAGES[code])


def is_admin(user):
    metadata = user.get("app_metadata") if isinstance(user, dict) else None
    return (
        isinstance(metadata, dict)
        and metadata.get("qe_role") == "admin"
        and metadata.get("qe_suspended") is not True
        and bool(user.get("email_confirmed_at"))
        and isinstance(user.get("email"), str)
        and bool(user["email"].strip())
    )


def require_admin():
    user = getattr(g, "auth_user", None) if has_request_context() else None
    if not isinstance(user, dict) or not is_admin(user):
        raise AdminError("admin_required", 403)
    return user


def require_owner():
    user = require_admin()
    if (user.get("app_metadata") or {}).get("qe_owner") is not True:
        raise AdminError("owner_required", 403)
    return user


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _service_request(method, path, body=None):
    from auth import settings

    url, _, _, _ = settings()
    parsed = urlsplit(url)
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if (
        not key
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise AdminError("admin_not_configured", 503)
    req = Request(
        f"{url}/auth/v1/admin/users{path}",
        method=method,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with build_opener(_NoRedirect()).open(req, timeout=8) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Response too large")
        if method == "DELETE" and not raw.strip():
            return {}
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Unexpected response")
        return result
    except HTTPError as error:
        if error.code == 404:
            raise AdminError("user_not_found", 404) from None
        if method == "DELETE":
            if error.code in (409, 422):
                raise AdminError("delete_blocked", 409) from None
            raise AdminError("delete_unconfirmed", 503) from None
        raise AdminError("admin_unavailable", 503) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise AdminError(
            "delete_unconfirmed" if method == "DELETE" else "admin_unavailable", 503
        ) from None


def _admin_request(method, path, body=None):
    # Authorization precedes access to privileged credentials.
    require_admin()
    return _service_request(method, path, body)


def account_suspended(user, *, fail_closed=True):
    metadata = user.get("app_metadata") or {}
    if isinstance(metadata, dict) and metadata.get("qe_suspended") is True:
        return True
    until = user.get("banned_until")
    if not until:
        return False
    try:
        return datetime.fromisoformat(until.replace("Z", "+00:00")) > datetime.now(UTC)
    except (ValueError, TypeError, AttributeError):
        # A malformed suspension state must never grant access.
        return fail_closed


def _public_user(user):
    metadata = user.get("app_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    return {
        "id": user["id"],
        "email": user.get("email") or "No email",
        "role": "Admin" if metadata.get("qe_role") == "admin" else "Member",
        "owner": metadata.get("qe_owner") is True,
        "verification": "Verified" if user.get("email_confirmed_at") else "Unverified",
        "access": "Suspended" if account_suspended(user) else "Active",
        "created_at": user.get("created_at") or "",
        "last_sign_in_at": user.get("last_sign_in_at") or "Never",
    }


def list_users(page=1):
    require_admin()
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 100_000:
        raise AdminError("invalid_request", 400)
    data = _admin_request("GET", f"?page={page}&per_page={PAGE_SIZE}")
    users = data.get("users")
    if not isinstance(users, list) or len(users) > PAGE_SIZE:
        raise AdminError("admin_unavailable", 503)
    if any(not isinstance(user, dict) or not user.get("id") for user in users):
        raise AdminError("admin_unavailable", 503)
    return {
        "users": [_public_user(user) for user in users],
        "page": page,
        # A full final page may offer one empty next page; no unbounded scanning.
        "has_next": len(users) == PAGE_SIZE,
    }


def update_access(user_id, action):
    actor = require_admin()
    try:
        user_id = str(UUID(user_id))
    except (ValueError, TypeError, AttributeError):
        raise AdminError("invalid_request", 400) from None
    if action not in ("suspend", "restore", "grant_admin", "revoke_admin"):
        raise AdminError("invalid_request", 400)
    target = _admin_request("GET", f"/{user_id}")
    target = target.get("user", target)
    if not isinstance(target, dict) or target.get("id") != user_id:
        raise AdminError("admin_unavailable", 503)
    metadata = target.get("app_metadata") or {}
    if user_id == actor["id"]:
        raise AdminError("self_change", 403)
    if not isinstance(metadata, dict):
        raise AdminError("admin_unavailable", 503)
    if metadata.get("qe_owner") is True:
        raise AdminError("owner_protected", 403)
    if action == "suspend" and metadata.get("qe_role") == "admin":
        raise AdminError("protected_account", 403)
    if action == "grant_admin" and (
        not target.get("email_confirmed_at")
        or not isinstance(target.get("email"), str)
        or not target["email"].strip()
        or account_suspended(target)
    ):
        raise AdminError("verification_required", 403)
    if action in ("grant_admin", "revoke_admin"):
        body: dict[str, object] = {
            "app_metadata": {
                "qe_role": "admin" if action == "grant_admin" else "member"
            }
        }
        message = (
            "Administrator access granted."
            if action == "grant_admin"
            else "Administrator access revoked."
        )
    else:
        body = {
            "ban_duration": "876000h" if action == "suspend" else "none",
            "app_metadata": {"qe_suspended": action == "suspend"},
        }
        message = (
            "Account suspended." if action == "suspend" else "Account access restored."
        )
    require_access_guard()
    _admin_request("PUT", f"/{user_id}", body)
    # Supabase merges app_metadata; role changes and suspension are rechecked
    # against Supabase on each request, including existing application sessions.
    return message


def require_access_guard():
    require_admin()
    from password_auth import PasswordAuthError, _request

    try:
        result = _request(
            "/rest/v1/rpc/qe_administrator_guard_ready", {}, privileged=True
        )
    except PasswordAuthError:
        raise AdminError("access_guard_required", 503) from None
    if result.get("ready") is not True:
        raise AdminError("access_guard_required", 503)


def deletion_target(user_id):
    actor = require_owner()
    try:
        user_id = str(UUID(user_id))
    except (ValueError, TypeError, AttributeError):
        raise AdminError("invalid_request", 400) from None
    if user_id == actor["id"]:
        raise AdminError("self_change", 403)
    target = _admin_request("GET", f"/{user_id}")
    target = target.get("user", target)
    if not isinstance(target, dict) or target.get("id") != user_id:
        raise AdminError("admin_unavailable", 503)
    metadata = target.get("app_metadata") or {}
    if not isinstance(metadata, dict):
        raise AdminError("admin_unavailable", 503)
    if metadata.get("qe_owner") is True:
        raise AdminError("owner_protected", 403)
    if metadata.get("qe_role") == "admin":
        raise AdminError("admin_deletion_protected", 403)
    if not account_suspended(target, fail_closed=False):
        raise AdminError("suspension_required", 409)
    if not isinstance(target.get("email"), str) or not target["email"].strip():
        raise AdminError("invalid_request", 400)
    return target


def require_deletion_guard():
    require_owner()
    from password_auth import PasswordAuthError, _request

    try:
        status = _request(
            "/rest/v1/rpc/qe_account_deletion_guard_ready", {}, privileged=True
        )
    except PasswordAuthError:
        raise AdminError("delete_guard_required", 503) from None
    if status.get("ready") is not True:
        raise AdminError("delete_guard_required", 503)


def delete_account(user_id, confirmation_email):
    # Re-read the target at confirmation; client selection is never authority.
    target = deletion_target(user_id)
    if (
        not isinstance(confirmation_email, str)
        or confirmation_email.strip().casefold() != target["email"].strip().casefold()
    ):
        raise AdminError("confirmation_mismatch", 400)
    require_deletion_guard()
    _admin_request("DELETE", f"/{target['id']}", {"should_soft_delete": False})
    return "Account deleted."


def install_admin_routes(server):
    @server.errorhandler(AdminError)
    def handle_admin_error(error):
        return jsonify(error=error.code, message=str(error)), error.status

    @server.get("/api/admin/users")
    def admin_directory():
        require_admin()
        try:
            page = int(request.args.get("page", "1"))
        except ValueError:
            raise AdminError("invalid_request", 400) from None
        return jsonify(list_users(page))

    @server.delete("/api/admin/users/<user_id>")
    def admin_delete_account(user_id):
        require_owner()
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != {"confirmation_email"}:
            raise AdminError("invalid_request", 400)
        return jsonify(message=delete_account(user_id, body["confirmation_email"]))

    @server.patch("/api/admin/users/<user_id>")
    def admin_access(user_id):
        require_admin()
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != {"action"}:
            raise AdminError("invalid_request", 400)
        return jsonify(message=update_access(user_id, body["action"]))
