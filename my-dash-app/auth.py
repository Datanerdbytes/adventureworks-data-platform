"""Temporary dash-auth HTTP Basic authentication for the local workspace.

Public marketing pages are Flask routes, never public Dash callbacks. The strict
boundary prevents a caller-supplied pathname from bypassing callback protection.
"""

import base64
import binascii
import hmac
import os
import secrets
from datetime import timedelta
from urllib.parse import urlencode
from pathlib import Path

from dash_auth import BasicAuth
from dotenv import load_dotenv
from flask import Response, g, request, session, redirect, render_template

PUBLIC_PATHS = frozenset({"/", "/theme.css", "/assets/landing.css"})


class WorkspaceBasicAuth(BasicAuth):
    def _protect(self):
        # install_auth registers the guard before Dash's own request hooks.
        pass

    def is_authorized(self):
        header = request.headers.get("Authorization", "")
        try:
            scheme, encoded = header.split(" ", 1)
            if scheme.lower() != "basic":
                return False
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
            username, password = decoded.split(":", 1)
        except (ValueError, UnicodeError, binascii.Error):
            return False
        if not self._auth_func(username, password):
            return False
        g.workspace_username = username
        return True

    def login_request(self):
        return Response(
            "Sign in with your workspace credentials to continue.",
            status=401,
            headers={
                "WWW-Authenticate": 'Basic realm="AdventureWorks Analytics", charset="UTF-8"'
            },
            mimetype="text/plain",
        )


def install_auth(server):
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    server.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("AUTH_APP_ORIGIN", "").startswith(
            "https://"
        ),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_REFRESH_EACH_REQUEST=False,
        DASH_AUTH_USERNAME=os.environ.get("DASH_AUTH_USERNAME", ""),
        DASH_AUTH_PASSWORD=os.environ.get("DASH_AUTH_PASSWORD", ""),
    )

    def credential_version():
        value = (
            server.config["DASH_AUTH_USERNAME"]
            + "\0"
            + server.config["DASH_AUTH_PASSWORD"]
        )
        return hmac.new(
            server.secret_key.encode(), value.encode(), "sha256"
        ).hexdigest()

    def origin_matches():
        return request.headers.get("Origin") == os.environ.get(
            "AUTH_APP_ORIGIN", request.host_url.rstrip("/")
        )

    def next_page(value):
        allowed = {
            "/dashboard",
            "/monitoring",
            "/tables",
            "/settings",
            "/dashboard/executive",
            "/dashboard/wholesale",
            "/dashboard/growth",
            "/dashboard/customers",
        }
        return value if value in allowed else "/dashboard"

    @server.route("/login", methods=["GET", "POST"])
    def login():
        destination = next_page(request.values.get("next"))
        error = None
        status = 200
        if request.method == "POST":
            csrf = request.form.get("csrf", "")
            if (
                not origin_matches()
                or not csrf
                or not hmac.compare_digest(csrf, session.get("login_csrf", ""))
            ):
                return Response(
                    "Invalid sign-in request. Reload the sign-in page and retry.",
                    status=403,
                )
            if (
                not server.config["DASH_AUTH_USERNAME"]
                or not server.config["DASH_AUTH_PASSWORD"]
            ):
                error, status = (
                    "Workspace sign-in is not configured on the server.",
                    503,
                )
            elif server.extensions["workspace_auth"]._auth_func(
                request.form.get("username", ""), request.form.get("password", "")
            ):
                session.clear()
                session.permanent = True
                session["workspace_user"] = server.config["DASH_AUTH_USERNAME"]
                session["credential_version"] = credential_version()
                return redirect(destination, code=303)
            else:
                error, status = (
                    "The username or password is incorrect. Please try again.",
                    401,
                )
        session["login_csrf"] = secrets.token_urlsafe(32)
        return (
            render_template(
                "login.html", csrf=session["login_csrf"], next=destination, error=error
            ),
            status,
        )

    @server.before_request
    def protect_workspace():
        if request.path == "/login" and request.method in ("GET", "HEAD", "POST"):
            return None
        if request.path in PUBLIC_PATHS and request.method in ("GET", "HEAD"):
            return None
        if not all(
            server.config.get(key)
            for key in ("DASH_AUTH_USERNAME", "DASH_AUTH_PASSWORD")
        ):
            return Response(
                "Workspace sign-in is not configured. Set DASH_AUTH_USERNAME and DASH_AUTH_PASSWORD on the server.",
                status=503,
                mimetype="text/plain",
            )
        auth = server.extensions["workspace_auth"]
        session_ok = session.get("workspace_user") == server.config[
            "DASH_AUTH_USERNAME"
        ] and hmac.compare_digest(
            session.get("credential_version", ""), credential_version()
        )
        if session_ok:
            g.workspace_username = session["workspace_user"]
        elif not auth.is_authorized():
            if (
                request.method == "GET"
                and "text/html" in request.headers.get("Accept", "")
                and not request.path.startswith(("/_dash", "/assets/", "/theme.css"))
            ):
                return redirect(
                    "/login?" + urlencode({"next": next_page(request.path)})
                )
            return auth.login_request()
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("Origin")
            expected = os.environ.get("AUTH_APP_ORIGIN", request.host_url.rstrip("/"))
            if origin != expected:
                return Response("Request origin is not allowed.", status=403)
        return None

    @server.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def configure_auth(app):
    def verify(username, password):
        config = app.server.config
        user_matches = hmac.compare_digest(
            username.encode(), config["DASH_AUTH_USERNAME"].encode()
        )
        password_matches = hmac.compare_digest(
            password.encode(), config["DASH_AUTH_PASSWORD"].encode()
        )
        return user_matches and password_matches

    app.server.extensions["workspace_auth"] = WorkspaceBasicAuth(app, auth_func=verify)
