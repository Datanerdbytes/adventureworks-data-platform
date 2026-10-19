"""Supabase identity and account access guard, installed before Dash hooks."""

import os
import base64
import json
import secrets
import hashlib
import hmac
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

from dotenv import load_dotenv
from flask import (
    current_app,
    g,
    has_app_context,
    jsonify,
    redirect,
    render_template,
    request,
    session,
)
from itsdangerous import URLSafeTimedSerializer, BadSignature
from governance import GovernanceError, SupabaseGateway
from rate_limiter import init_limiter, enforce_user_limit
from password_auth import (
    PasswordAuthError,
    ensure_not_locked,
    password_sign_in,
    enabled as lockout_enabled,
)
from user_admin import account_suspended, install_admin_routes, is_admin

COOKIE = "aw_access"
CSRF_COOKIE = "aw_csrf"
CSRF_MAX_AGE = 86400


def csrf_signer():
    return URLSafeTimedSerializer(
        current_app.secret_key,
        salt="adventureworks-csrf-v1",
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def csrf_nonce():
    try:
        nonce = csrf_signer().loads(
            request.cookies.get(CSRF_COOKIE, ""), max_age=CSRF_MAX_AGE
        )
    except BadSignature:
        return None
    if (
        not isinstance(nonce, str)
        or len(nonce) != 64
        or any(c not in "0123456789abcdef" for c in nonce)
    ):
        return None
    return nonce


def csrf_token(nonce):
    # Bind the signed security session to the current authentication cookie.
    # No access token is stored in the security cookie or Flask session.
    access_digest = hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest()
    key = current_app.secret_key
    if isinstance(key, str):
        key = key.encode()
    return hmac.new(
        key, ("csrf-v1:" + nonce + ":" + access_digest).encode(), hashlib.sha256
    ).hexdigest()


def valid_csrf_token(token):
    nonce = csrf_nonce()
    return (
        nonce is not None
        and isinstance(token, str)
        and len(token) == 64
        and all(c in "0123456789abcdef" for c in token)
        and secrets.compare_digest(csrf_token(nonce), token)
    )


AUTH_PAGES = {
    "/login": "login",
    "/signup": "signup",
    "/auth/recovery": "recovery",
    "/auth/callback": "callback",
}
PUBLIC_ASSETS = frozenset(
    {
        "/theme.css",
        "/assets/landing.css",
        "/assets/auth.css",
        "/assets/auth.js",
        "/assets/auth-google.png",
        "/assets/auth-github.svg",
    }
)
SAFE_NEXT = frozenset(
    {
        "/dashboard",
        "/workspace",
        "/admin/users",
        "/monitoring",
        "/tables",
        "/settings",
        "/dashboard/executive",
        "/dashboard/wholesale",
        "/dashboard/growth",
        "/dashboard/customers",
    }
)


def safe_next(value):
    return value if value in SAFE_NEXT else "/dashboard"


def auth_configuration_error(config):
    key = config.get("SUPABASE_PUBLIC_KEY", "")
    if key.startswith("sb_secret_"):
        return "Only a public Supabase key is allowed in browser configuration."
    if key.count(".") == 2:
        try:
            payload = key.split(".")[1]
            claims = json.loads(
                base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
            )
            if not isinstance(claims, dict) or claims.get("role") != "anon":
                return "Only an anon or publishable key is allowed in browser configuration."
        except (ValueError, UnicodeError):
            return "Invalid Supabase public key."
    origin = urlparse(config.get("AUTH_APP_ORIGIN", ""))
    local = (
        origin.hostname in ("localhost", "127.0.0.1", "::1") and origin.scheme == "http"
    )
    url = urlparse(config.get("SUPABASE_URL", ""))
    if not config.get("SUPABASE_PUBLIC_KEY") or not config.get(
        "AUTH_SECRET_CONFIGURED"
    ):
        return "Authentication configuration is incomplete."
    if origin.scheme != "https" and not local:
        return "Configure HTTPS or explicit HTTP localhost development."
    if (
        not origin.netloc
        or origin.path
        or origin.query
        or origin.fragment
        or origin.username
    ):
        return "Configure an exact application origin."
    if url.scheme != "https" and not (
        local and url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1")
    ):
        return "Configure a valid Supabase URL."
    if not url.netloc or url.username or url.query or url.fragment:
        return "Configure a valid Supabase URL."
    return None


def settings():
    config = (
        current_app.config
        if has_app_context()
        else {
            "SUPABASE_URL": os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/"),
            "SUPABASE_PUBLIC_KEY": os.environ.get(
                "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"
            )
            or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", ""),
            "AUTH_APP_ORIGIN": os.environ.get("AUTH_APP_ORIGIN", "").rstrip("/"),
            "AUTH_SECRET_CONFIGURED": bool(os.environ.get("FLASK_SECRET_KEY")),
            "SESSION_COOKIE_SECURE": not os.environ.get(
                "AUTH_APP_ORIGIN", ""
            ).startswith("http://"),
        }
    )
    error = auth_configuration_error(config)
    if error:
        raise GovernanceError(error)
    return (
        config["SUPABASE_URL"],
        config["SUPABASE_PUBLIC_KEY"],
        config["AUTH_APP_ORIGIN"],
        config["SESSION_COOKIE_SECURE"],
    )


def token_lifetime(token):
    # Called only after remote Auth verification. Claims never authorize roles.
    try:
        payload = token.split(".")[1]
        claims = json.loads(
            base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        )
        remaining = int(claims["exp"]) - int(time.time())
    except (ValueError, KeyError, IndexError, TypeError):
        raise GovernanceError("Your session is invalid or expired.", 401) from None
    if remaining <= 0:
        raise GovernanceError("Your session is invalid or expired.", 401)
    return min(remaining, 3600)


def install_auth(server):
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    origin = os.environ.get("AUTH_APP_ORIGIN", "").rstrip("/")
    server.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
        AUTH_SECRET_CONFIGURED=bool(os.environ.get("FLASK_SECRET_KEY")),
        SUPABASE_URL=os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/"),
        SUPABASE_PUBLIC_KEY=(
            os.environ.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
            or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
        ),
        AUTH_APP_ORIGIN=origin,
        AUTH_PROVIDERS=[
            p
            for p in ("google", "github")
            if p in os.environ.get("AUTH_OAUTH_PROVIDERS", "").split(",")
        ],
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not origin.startswith("http://"),
        SESSION_REFRESH_EACH_REQUEST=False,
    )
    server.extensions["supabase_gateway_factory"] = SupabaseGateway

    limiter = init_limiter(server)
    install_admin_routes(server)

    def configuration():
        error = auth_configuration_error(server.config)
        if error:
            raise GovernanceError(error)

    def gateway(token=None):
        configuration()
        token = token if token is not None else request.cookies.get(COOKIE)
        if not token or not isinstance(token, str) or len(token) > 3800:
            raise GovernanceError("Sign in to continue.", 401)
        return server.extensions["supabase_gateway_factory"](
            server.config["SUPABASE_URL"], server.config["SUPABASE_PUBLIC_KEY"], token
        )

    def load_identity(token=None):
        client = gateway(token)
        user = client.user()
        if account_suspended(user):
            raise GovernanceError("Account access is suspended.", 403)
        try:
            ensure_not_locked(user["email"])
        except PasswordAuthError as error:
            raise GovernanceError(
                (
                    "Account is temporarily locked."
                    if error.code == "account_locked"
                    else "Authentication is unavailable."
                ),
                403 if error.code == "account_locked" else 503,
            ) from None
        g.auth_user = user
        g.account_username = user["email"]
        enforce_user_limit(limiter, user)
        return client, user

    def origin_required():
        if request.headers.get("Origin") != server.config["AUTH_APP_ORIGIN"]:
            raise GovernanceError("Request origin is not allowed.", 403)

    def csrf_required():
        if not valid_csrf_token(request.headers.get("X-CSRF-Token")):
            raise GovernanceError(
                "CSRF token missing or invalid. Reload and retry.", 403
            )

    @server.get("/auth/csrf")
    @limiter.limit("600 per minute; 12000 per hour")
    def issue_csrf_token():
        try:
            configuration()
            if (
                request.headers.get("X-CSRF-Request") != "1"
                or request.headers.get("Sec-Fetch-Site") == "cross-site"
                or (
                    request.headers.get("Origin") is not None
                    and request.headers["Origin"] != server.config["AUTH_APP_ORIGIN"]
                )
            ):
                raise GovernanceError("Request origin is not allowed.", 403)
            nonce = csrf_nonce()
            needs_cookie = nonce is None
            if needs_cookie:
                nonce = secrets.token_hex(32)
            response = jsonify(csrfToken=csrf_token(nonce))
            if needs_cookie:
                response.set_cookie(
                    CSRF_COOKIE,
                    csrf_signer().dumps(nonce),
                    httponly=True,
                    secure=server.config["SESSION_COOKIE_SECURE"],
                    samesite="Lax",
                )
            return response
        except GovernanceError as error:
            return failure(error)

    def failure(error):
        return jsonify(error=str(error)), error.status

    @server.route("/auth/config", methods=["GET"])
    @limiter.limit("30 per minute; 100 per hour")
    def auth_config():
        try:
            configuration()
            return jsonify(
                url=server.config["SUPABASE_URL"],
                publicKey=server.config["SUPABASE_PUBLIC_KEY"],
                providers=server.config["AUTH_PROVIDERS"],
                passwordLockoutEnabled=lockout_enabled(),
            )
        except GovernanceError as error:
            return failure(error)

    @server.post("/auth/password")
    @limiter.limit("20 per minute; 100 per hour")
    def password_login():
        try:
            configuration()
            origin_required()
            csrf_required()
            if request.content_length and request.content_length > 8192:
                raise GovernanceError("Invalid sign-in request.", 400)
            body = request.get_json(silent=True)
            if not isinstance(body, dict) or set(body) != {"email", "password"}:
                raise GovernanceError("Invalid sign-in request.", 400)
            return jsonify(password_sign_in(body["email"], body["password"]))
        except GovernanceError as error:
            return failure(error)
        except PasswordAuthError as error:
            response = jsonify(error=error.code, retry_after=error.retry_after)
            response.status_code = error.status
            if error.retry_after:
                response.headers["Retry-After"] = str(error.retry_after)
            return response

    @server.route("/auth/session", methods=["POST", "DELETE"])
    @limiter.limit("30 per minute; 300 per hour", methods=["POST"], per_method=True)
    @limiter.limit("120 per minute; 600 per hour", methods=["DELETE"], per_method=True)
    def auth_session():
        may_clear_cookie = False
        try:
            configuration()
            origin_required()
            csrf_required()
            may_clear_cookie = True
            if request.method == "DELETE":
                session.clear()
                response = jsonify(signedOut=True)
                response.delete_cookie(
                    CSRF_COOKIE,
                    httponly=True,
                    samesite="Lax",
                    secure=server.config["SESSION_COOKIE_SECURE"],
                )
                response.delete_cookie(
                    COOKIE,
                    httponly=True,
                    samesite="Lax",
                    secure=server.config["SESSION_COOKIE_SECURE"],
                )
                return response
            payload = request.get_json(silent=True) or {}
            if not isinstance(payload, dict):
                raise GovernanceError("Invalid session request.", 400)
            token = payload.get("access_token")
            if not isinstance(token, str) or not token:
                raise GovernanceError("A valid access token is required.", 401)
            client, user = load_identity(token)
            remaining = token_lifetime(token)
            session.clear()  # Discard any legacy selected-workspace session.
            response = jsonify(
                approved=True,
                user={"email": user["email"]},
                next=safe_next(payload.get("next")),
            )
            response.set_cookie(
                COOKIE,
                payload["access_token"],
                max_age=remaining,
                httponly=True,
                secure=server.config["SESSION_COOKIE_SECURE"],
                samesite="Lax",
            )
            return response
        except GovernanceError as error:
            response, status = failure(error)
            if may_clear_cookie:
                response.delete_cookie(
                    COOKIE,
                    httponly=True,
                    samesite="Lax",
                    secure=server.config["SESSION_COOKIE_SECURE"],
                )
            return response, status

    @server.get("/auth/status")
    @limiter.limit("120 per minute; 600 per hour")
    def auth_status():
        try:
            client, user = load_identity()
            return jsonify(
                email=user["email"],
                admin=is_admin(user),
                owner=(user.get("app_metadata") or {}).get("qe_owner") is True,
            )
        except GovernanceError as error:
            return failure(error)

    def auth_page():
        return render_template(
            "auth.html",
            mode=AUTH_PAGES[request.path],
            next=safe_next(request.args.get("next")),
        )

    @limiter.limit("20 per minute; 60 per hour")
    def auth_page_limited():
        return auth_page()

    for path in AUTH_PAGES:
        server.add_url_rule(
            path,
            endpoint="auth_page_" + AUTH_PAGES[path],
            view_func=auth_page_limited,
            methods=["GET"],
        )

    @server.before_request
    def protect_accounts():
        if request.path in AUTH_PAGES and request.method in ("GET", "HEAD"):
            return None
        if request.path in PUBLIC_ASSETS and request.method in ("GET", "HEAD"):
            return None
        if (
            request.path in ("/auth/config", "/auth/status", "/auth/csrf")
            and request.method in ("GET", "HEAD")
        ) or (
            request.path in ("/auth/session", "/auth/password")
            and request.method in ("POST", "DELETE")
        ):
            return None  # Endpoints enforce their own identity/origin requirements.
        if (
            request.path == "/"
            and request.method in ("GET", "HEAD")
            and not request.cookies.get(COOKIE)
        ):
            return None
        try:
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                configuration()
                if not request.cookies.get(COOKIE):
                    raise GovernanceError("Sign in to continue.", 401)
                origin_required()
                csrf_required()
            client, _ = load_identity()
            if request.path == "/":
                return redirect("/dashboard")
            if request.path.startswith("/workspace/admin") or request.path in {
                "/auth/workspace",
                "/auth/registration",
                "/auth/access-pending",
            }:
                raise GovernanceError("Workspace governance has been retired.", 410)
            if (
                request.path == "/admin/users" or request.path.startswith("/api/admin/")
            ) and not is_admin(g.auth_user):
                raise GovernanceError("Administrator access required.", 403)
        except GovernanceError as error:
            if (
                request.method == "GET"
                and "text/html" in request.headers.get("Accept", "")
                and error.status in (401, 403)
            ):
                destination = (
                    "/login?" + urlencode({"next": safe_next(request.path)})
                    if error.status == 401
                    else "/login"
                )
                return redirect(destination)
            return failure(error)
        return None

    @server.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
