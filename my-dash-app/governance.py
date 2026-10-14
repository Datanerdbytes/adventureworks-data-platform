"""Bounded Supabase REST access. Clients are request-local, never user-global."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.parse import urlencode, urlsplit


class GovernanceError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward bearer tokens or API keys to a redirected authority.
        return None


def urlopen(request, timeout):
    """Keep the patchable transport boundary, with redirects disabled."""
    _validate_service_url(request.full_url, allow_request_path=True)
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


def _validate_service_url(url, allow_request_path=False):
    if (
        not isinstance(url, str)
        or "\\" in url
        or any(char.isspace() or ord(char) < 32 for char in url)
    ):
        raise GovernanceError("Invalid authentication service URL.")
    try:
        parsed = urlsplit(url)
        _ = parsed.port  # Reject malformed ports before creating a request.
    except ValueError:
        raise GovernanceError("Invalid authentication service URL.") from None
    local_http = parsed.scheme == "http" and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }
    if (
        (parsed.scheme != "https" and not local_http)
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or (not allow_request_path and parsed.path not in ("", "/"))
        or (not allow_request_path and parsed.query)
        or parsed.fragment
    ):
        raise GovernanceError("Invalid authentication service URL.")


class SupabaseGateway:
    def __init__(self, url, public_key, token):
        _validate_service_url(url)
        self.url, self.public_key, self.token = url.rstrip("/"), public_key, token

    def request(self, path, payload=None):
        _validate_service_url(self.url)
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or path.startswith("//")
            or "#" in path
            or any(char.isspace() or ord(char) < 32 for char in path)
        ):
            raise GovernanceError("Invalid authentication service path.")
        headers = {"apikey": self.public_key, "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = Request(
            self.url + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers=headers,
            method="GET" if payload is None else "POST",
        )
        try:
            with urlopen(request, timeout=8) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise GovernanceError(
                        "Authentication service returned too much data."
                    )
                return json.loads(raw) if raw else None
        except HTTPError as error:
            if path == "/auth/v1/user" and error.code in (400, 401, 403):
                raise GovernanceError(
                    "Your session is invalid or expired.", 401
                ) from None
            try:
                data = json.loads(error.read(4096))
            except (ValueError, OSError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            if data.get("code") == "42501" or error.code == 403:
                raise GovernanceError(
                    "You do not have permission for this action.", 403
                ) from None
            if error.code == 400 and data.get("code") in (
                "22023",
                "23514",
                "23502",
                "23505",
            ):
                messages = {
                    "Cannot remove the last active owner",
                    "Initial owner must have a confirmed account",
                    "Use member controls for an existing membership",
                    "Pending approval not found",
                    "Member not found",
                    "Invalid role",
                    "Invalid role or status",
                    "Invalid offset",
                    "Registration link is unavailable",
                    "Request is no longer pending",
                    "Invalid decision",
                    "A verified account is required",
                    "The user must sign up and verify this email before workspace approval.",
                }
                message = data.get("message")
                raise GovernanceError(
                    message if message in messages else "Check the supplied fields.",
                    400,
                ) from None
            raise GovernanceError(
                "Authentication or workspace service is unavailable."
            ) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise GovernanceError(
                "Authentication or workspace service is unavailable."
            ) from None

    def user(self):
        user = self.request("/auth/v1/user")
        if not isinstance(user, dict) or not user.get("id") or not user.get("email"):
            raise GovernanceError("A verified account with an email is required.", 403)
        if not user.get("email_confirmed_at"):
            raise GovernanceError(
                "Confirm your email before accessing the workspace.", 403
            )
        return user

    def rpc(self, name, **payload):
        return self.request("/rest/v1/rpc/" + name, payload)

    def has_revoked_membership(self, user_id):
        # RLS permits users to read their own memberships, including revoked ones.
        query = urlencode(
            {
                "select": "workspace_id",
                "user_id": "eq." + user_id,
                "active": "eq.false",
                "limit": "1",
            }
        )
        rows = self.request("/rest/v1/workspace_memberships?" + query)
        if not isinstance(rows, list):
            raise GovernanceError("Workspace service is unavailable.")
        return bool(rows)
