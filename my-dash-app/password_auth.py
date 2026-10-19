"""Shared password-attempt leases and sign-in gateway. Never log credentials."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID


class PasswordAuthError(Exception):
    def __init__(self, code, status=503, retry_after=0):
        self.code, self.status, self.retry_after = code, status, retry_after
        super().__init__(code)


def enabled():
    return os.getenv("AUTH_PASSWORD_LOCKOUT_ENABLED", "false").lower() == "true"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(path, body, privileged=False):
    from auth import settings

    url, anon, _, _ = settings()
    parsed = urlsplit(url)
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") if privileged else anon
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
        raise PasswordAuthError("lockout_not_configured")
    headers = {"apikey": key, "Content-Type": "application/json"}
    if privileged:
        headers["Authorization"] = f"Bearer {key}"
    req = Request(
        f"{url}{path}", data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with build_opener(_NoRedirect()).open(req, timeout=8) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("Oversized auth response")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Invalid auth response")
        return result
    except HTTPError as error:
        if not privileged and error.code == 400:
            try:
                details = json.loads(error.read(4096))
            except (ValueError, OSError):
                details = {}
            code = (
                (details.get("code") or details.get("error_code"))
                if isinstance(details, dict)
                else None
            )
            if code == "invalid_credentials":
                raise PasswordAuthError("invalid_credentials", 401) from None
            if code == "email_not_confirmed":
                raise PasswordAuthError("email_confirmation_required", 403) from None
            if code == "user_banned":
                raise PasswordAuthError("account_suspended", 403) from None
        if not privileged and error.code == 429:
            raise PasswordAuthError("rate_limited", 429, 60) from None
        raise PasswordAuthError("auth_unavailable") from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise PasswordAuthError("auth_unavailable") from None


def attempt(email, action, attempt_id=None, valid=None):
    result = _request(
        "/rest/v1/rpc/qe_password_attempt",
        {
            "p_email": email,
            "p_action": action,
            "p_attempt": attempt_id,
            "p_valid": valid,
        },
        privileged=True,
    )
    if not isinstance(result.get("allowed"), bool):
        raise PasswordAuthError("auth_unavailable")
    retry = result.get("retry_after")
    if isinstance(retry, bool) or not isinstance(retry, int) or not 0 <= retry <= 900:
        raise PasswordAuthError("auth_unavailable")
    if not result["allowed"] and result.get("error") not in {
        "account_locked",
        "attempt_in_progress",
        "attempt_expired",
        "invalid_credentials",
        "auth_unavailable",
    }:
        raise PasswordAuthError("auth_unavailable")
    return result


def _require_allowed(result):
    if result["allowed"]:
        return
    code = result["error"]
    raise PasswordAuthError(
        code,
        (
            423
            if code == "account_locked"
            else (
                429
                if code in {"attempt_in_progress", "attempt_expired"}
                else 401 if code == "invalid_credentials" else 503
            )
        ),
        result["retry_after"],
    )


def ensure_not_locked(email):
    if enabled():
        _require_allowed(attempt(email, "status"))


def password_sign_in(email, password):
    if not enabled():
        raise PasswordAuthError("lockout_not_configured")
    if (
        not isinstance(email, str)
        or not 3 <= len(email.strip()) <= 254
        or "@" not in email
        or not isinstance(password, str)
        or not 1 <= len(password) <= 4096
    ):
        raise PasswordAuthError("invalid_request", 400)
    email = email.strip().lower()
    started = attempt(email, "start")
    _require_allowed(started)
    try:
        lease = str(UUID(started.get("attempt_id", "")))
    except (ValueError, TypeError, AttributeError):
        raise PasswordAuthError("auth_unavailable") from None
    try:
        session = _request(
            "/auth/v1/token?grant_type=password", {"email": email, "password": password}
        )
    except PasswordAuthError as error:
        # Only Supabase's explicit invalid_credentials response counts as a wrong password.
        settled = attempt(
            email,
            "finish",
            lease,
            False if error.code == "invalid_credentials" else None,
        )
        if error.code == "invalid_credentials":
            _require_allowed(settled)
        raise
    if not all(
        isinstance(session.get(k), str) and session[k]
        for k in ("access_token", "refresh_token")
    ):
        attempt(email, "finish", lease, None)
        raise PasswordAuthError("auth_unavailable")
    settled = attempt(email, "finish", lease, True)
    _require_allowed(settled)
    return {
        "access_token": session["access_token"],
        "refresh_token": session["refresh_token"],
    }
