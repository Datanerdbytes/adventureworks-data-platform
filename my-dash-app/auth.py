"""Supabase identity and database membership guard, installed before Dash hooks."""

import os
import base64
import json
import secrets
from pathlib import Path
from urllib.parse import urlencode, urlparse

from dotenv import load_dotenv
from flask import Response, g, jsonify, redirect, render_template, request, session
from governance import GovernanceError, SupabaseGateway
from rate_limiter import init_limiter, limit_ip, limit_user

COOKIE = "aw_access"
AUTH_PAGES = {
    "/login": "login",
    "/signup": "signup",
    "/auth/recovery": "recovery",
    "/auth/callback": "callback",
    "/auth/access-pending": "pending",
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
        "/workspace/admin",
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
    
    # Initialize Flask-Limiter with Redis for production, memory for local dev/tests
    init_limiter(server)

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
        g.auth_user, g.governance = user, client
        g.workspace_username = user["email"]
        return client, user

    def load_context(client):
        context = client.rpc("workspace_context")
        if not isinstance(context, dict) or not isinstance(
            context.get("workspaces"), list
        ):
            raise GovernanceError("Workspace service returned an invalid response.")
        workspaces = context["workspaces"]
        if any(
            not isinstance(w, dict)
            or not isinstance(w.get("id"), str)
            or w.get("role") not in ("owner", "admin", "viewer", "platform_admin")
            or not all(
                isinstance(w.get(field), str)
                for field in ("name", "purpose", "responsible_team")
            )
            or not isinstance(w.get("owners"), list)
            for w in workspaces
        ):
            raise GovernanceError("Workspace service returned an invalid response.")
        selected = session.get("workspace_id")
        workspace = next((w for w in workspaces if w["id"] == selected), None)
        if workspace is None and workspaces:
            workspace = workspaces[0]
            session["workspace_id"] = workspace["id"]
        g.workspace_context, g.workspace = context, workspace
        return workspace

    def origin_required():
        if request.headers.get("Origin") != server.config["AUTH_APP_ORIGIN"]:
            raise GovernanceError("Request origin is not allowed.", 403)

    def failure(error):
        return jsonify(error=str(error)), error.status

    @server.route("/auth/config", methods=["GET"])
    @limit_ip(["30 per minute", "100 per hour"])
    def auth_config():
        try:
            configuration()
            return jsonify(
                url=server.config["SUPABASE_URL"],
                publicKey=server.config["SUPABASE_PUBLIC_KEY"],
                providers=server.config["AUTH_PROVIDERS"],
            )
        except GovernanceError as error:
            return failure(error)

    @server.get("/auth/registration")
    @limit_ip(["20 per minute", "60 per hour"])
    def registration_workspace():
        try:
            configuration()
            code = request.args.get("workspace")
            if code is not None and (
                len(code) != 48 or any(c not in "0123456789abcdef" for c in code)
            ):
                raise GovernanceError("Registration link is unavailable", 400)
            client = server.extensions["supabase_gateway_factory"](
                server.config["SUPABASE_URL"],
                server.config["SUPABASE_PUBLIC_KEY"],
                None,
            )
            target = client.rpc("registration_workspace", p_code=code)
            if (
                not isinstance(target, dict)
                or (
                    target.get("code") is not None
                    and not isinstance(target.get("code"), str)
                )
                or not isinstance(target.get("name"), str)
            ):
                raise GovernanceError("Registration link is unavailable", 400)
            return jsonify(target)
        except GovernanceError as error:
            return failure(error)

    @server.route("/auth/session", methods=["POST", "DELETE"])
    @limit_ip(["10 per minute", "30 per hour"], methods=["POST"])
    @limit_user(["30 per minute", "100 per hour"], methods=["DELETE"])
    def auth_session():
        try:
            configuration()
            origin_required()
            if request.method == "DELETE":
                session.clear()
                response = jsonify(signedOut=True)
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
            # Membership is granted transactionally by the reviewing administrator.
            workspace = load_context(client)
            response = jsonify(
                approved=workspace is not None,
                user={"email": user["email"]},
                requestStatus=(
                    (
                        "revoked"
                        if client.has_revoked_membership(user["id"])
                        else client.rpc("my_access_request_status")
                    )
                    if workspace is None
                    else None
                ),
                next=(
                    safe_next(payload.get("next"))
                    if workspace
                    else "/auth/access-pending"
                ),
            )
            if workspace is None:
                session.clear()
                response.delete_cookie(
                    COOKIE,
                    httponly=True,
                    secure=server.config["SESSION_COOKIE_SECURE"],
                    samesite="Lax",
                )
                return response
            response.set_cookie(
                COOKIE,
                payload["access_token"],
                max_age=3600,
                httponly=True,
                secure=server.config["SESSION_COOKIE_SECURE"],
                samesite="Lax",
            )
            return response
        except GovernanceError as error:
            return failure(error)

    @server.get("/auth/status")
    @limit_user(["60 per minute", "200 per hour"])
    def auth_status():
        try:
            client, user = load_identity()
            workspace = load_context(client)
            if workspace is None:
                raise GovernanceError(
                    "Your account has no approved workspace membership.", 403
                )
            return jsonify(
                email=user["email"],
                workspace=workspace,
                platformAdmin=g.workspace_context.get("platform_admin", False),
            )
        except GovernanceError as error:
            return failure(error)

    @server.post("/auth/workspace")
    @limit_user(["30 per minute", "100 per hour"])
    def select_workspace():
        try:
            origin_required()
            client, _ = load_identity()
            load_context(client)
            payload = request.get_json(silent=True) or {}
            if not isinstance(payload, dict):
                raise GovernanceError("Invalid workspace selection.", 400)
            selected = payload.get("workspace_id")
            if not any(w["id"] == selected for w in g.workspace_context["workspaces"]):
                raise GovernanceError("Workspace access denied.", 403)
            session["workspace_id"] = selected
            return jsonify(next="/workspace")
        except GovernanceError as error:
            return failure(error)

    def auth_page():
        return render_template(
            "auth.html",
            mode=AUTH_PAGES[request.path],
            next=safe_next(request.args.get("next")),
        )

    @limit_ip(["20 per minute", "60 per hour"])
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
    def protect_workspace():
        if request.path in AUTH_PAGES and request.method in ("GET", "HEAD"):
            return None
        if request.path in PUBLIC_ASSETS and request.method in ("GET", "HEAD"):
            return None
        if (
            request.path in ("/auth/config", "/auth/status", "/auth/registration")
            and request.method in ("GET", "HEAD")
        ) or (
            request.path in ("/auth/session", "/auth/workspace")
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
            client, _ = load_identity()
            workspace = load_context(client)
            if workspace is None:
                raise GovernanceError(
                    "Your account has no approved workspace membership.", 403
                )
            if request.path == "/":
                return redirect("/dashboard")
            if request.path == "/workspace/admin" and workspace["role"] not in (
                "owner",
                "admin",
                "platform_admin",
            ):
                raise GovernanceError("Workspace administration access denied.", 403)
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                origin_required()
        except GovernanceError as error:
            if (
                request.method == "GET"
                and "text/html" in request.headers.get("Accept", "")
                and error.status in (401, 403)
            ):
                destination = (
                    "/login?" + urlencode({"next": safe_next(request.path)})
                    if error.status == 401
                    else "/auth/access-pending"
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
