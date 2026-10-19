"""Offline Supabase fixtures. Never used by application code."""

from governance import GovernanceError
import base64
import json
import time


def token(kind="approved", lifetime=3600):
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"exp": int(time.time()) + lifetime, "fixture": kind}).encode()
        )
        .decode()
        .rstrip("=")
    )
    return "fixture." + payload + ".signature"


WORKSPACE = {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "Test Workspace",
    "purpose": "Reporting",
    "responsible_team": "Governance Team",
    "role": "owner",
    "owners": ["owner@example.test"],
}
CONFIG = dict(
    SUPABASE_URL="https://project.supabase.co",
    SUPABASE_PUBLIC_KEY="test-public-key",
    AUTH_APP_ORIGIN="http://localhost",
    AUTH_SECRET_CONFIGURED=True,
    SESSION_COOKIE_SECURE=False,
    AUTH_PROVIDERS=[],
)


class FakeGateway:
    calls = []

    def __init__(self, url, key, token):
        self.token = token
        if token and token.startswith("fixture."):
            payload = token.split(".")[1]
            self.token = json.loads(
                base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
            )["fixture"]

    def user(self):
        if self.token in ("expired", "tampered"):
            raise GovernanceError("Invalid session.", 401)
        if self.token == "outage":
            raise GovernanceError("Service unavailable.")
        if self.token == "unconfirmed":
            raise GovernanceError("Confirm email.", 403)
        return {
            "id": "22222222-2222-2222-2222-222222222222",
            "email": "owner@example.test",
            "email_confirmed_at": "2026-10-12",
            "app_metadata": {
                "qe_role": "member" if self.token == "viewer" else "admin",
                "qe_owner": self.token != "viewer",
                "qe_suspended": self.token == "suspended",
            },
        }

    def rpc(self, name, **payload):
        self.calls.append((name, payload))
        if name == "registration_workspace":
            return {"name": WORKSPACE["name"], "code": "a" * 48}
        if name == "create_workspace":
            return "33333333-3333-3333-3333-333333333333"
        if name == "my_access_request_status":
            return "pending"
        if name == "workspace_context":
            if self.token in ("no-member", "revoked"):
                return {"workspaces": [], "platform_admin": False}
            workspace = {
                **WORKSPACE,
                "role": "viewer" if self.token == "viewer" else "owner",
            }
            return {
                "workspaces": [workspace],
                "platform_admin": self.token == "platform",
            }
        if name == "workspace_members_directory":
            return {
                "members": [
                    {
                        "workspace_id": WORKSPACE["id"],
                        "workspace_name": WORKSPACE["name"],
                        "user_id": "44444444-4444-4444-4444-444444444444",
                        "email": "member@example.test",
                        "role": "viewer",
                        "active": True,
                        "email_confirmed": True,
                        "created_at": "2026-10-12T00:00:00Z",
                        "updated_at": "2026-10-12T00:00:00Z",
                    }
                ],
                "total": 1,
                "offset": 0,
            }
        if name == "workspace_governance_activity":
            return {"events": [], "total": 0, "offset": 0}
        if name == "workspace_admin_data":
            return {
                "members": [],
                "approvals": [],
                "events": [],
                "member_count": 0,
                "approval_count": 0,
            }
        return None

    def has_revoked_membership(self, user_id):
        return self.token == "revoked"


def csrf_headers(client):
    response = client.get("/auth/csrf", headers={"X-CSRF-Request": "1"})
    return {
        "Origin": "http://localhost",
        "X-CSRF-Token": (response.json or {}).get("csrfToken", ""),
    }
