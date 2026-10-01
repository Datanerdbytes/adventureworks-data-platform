"""Temporary dash-auth HTTP Basic authentication for the local workspace.

Public marketing pages are Flask routes, never public Dash callbacks. The strict
boundary prevents a caller-supplied pathname from bypassing callback protection.
"""

import base64
import binascii
import hmac
import os
from pathlib import Path

from dash_auth import BasicAuth
from dotenv import load_dotenv
from flask import Response, g, request

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
        DASH_AUTH_USERNAME=os.environ.get("DASH_AUTH_USERNAME", ""),
        DASH_AUTH_PASSWORD=os.environ.get("DASH_AUTH_PASSWORD", ""),
    )

    @server.before_request
    def protect_workspace():
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
        if not auth.is_authorized():
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
