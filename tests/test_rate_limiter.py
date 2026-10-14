"""Offline auth throttling and storage/proxy safety regression tests."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from limits.storage import MemoryStorage
from redis.exceptions import ConnectionError as RedisConnectionError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from auth import install_auth
from auth_fixtures import CONFIG, FakeGateway
from rate_limiter import USER_LIMITS


class CountingGateway(FakeGateway):
    validations = 0

    def user(self):
        type(self).validations += 1
        return super().user()


class RateLimitTests(unittest.TestCase):
    def make_app(self, environment=None):
        app = Flask(
            "rate-test",
            template_folder=str(
                Path(__file__).resolve().parents[1] / "my-dash-app" / "templates"
            ),
        )
        with (
            patch.dict(
                "os.environ",
                (
                    environment
                    if environment is not None
                    else {"RATE_LIMIT_ENVIRONMENT": "testing"}
                ),
                clear=True,
            ),
            patch("auth.load_dotenv"),
        ):
            install_auth(app)
        app.config.update(CONFIG, TESTING=True)
        app.extensions["supabase_gateway_factory"] = CountingGateway
        return app

    def setUp(self):
        self.app = self.make_app()
        self.client = self.app.test_client()
        self.limiter = self.app.extensions["auth_limiter"]
        CountingGateway.validations = 0
        FakeGateway.calls = []
        self.origin = {"Origin": "http://localhost"}

    def test_startup_and_all_auth_routes(self):
        for path in (
            "/login",
            "/signup",
            "/auth/recovery",
            "/auth/callback",
            "/auth/access-pending",
            "/auth/config",
            "/auth/registration",
        ):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.get("/auth/status").status_code, 401)

    def test_ip_rejection_precedes_supabase_and_returns_json(self):
        for _ in range(30):
            self.assertEqual(
                self.client.post(
                    "/auth/session",
                    json={"access_token": "approved"},
                    headers=self.origin,
                ).status_code,
                200,
            )
        validations = CountingGateway.validations
        calls = len(FakeGateway.calls)
        response = self.client.post(
            "/auth/session", json={"access_token": "approved"}, headers=self.origin
        )
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.is_json)
        self.assertIn("error", response.json)
        self.assertGreater(int(response.headers["Retry-After"]), 0)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertEqual(CountingGateway.validations, validations)
        self.assertEqual(len(FakeGateway.calls), calls)
        self.assertNotIn("approved", response.get_data(as_text=True))

    def test_endpoint_and_method_isolation_and_logout(self):
        for _ in range(31):
            self.client.post("/auth/session", json={}, headers=self.origin)
        self.assertEqual(self.client.get("/auth/config").status_code, 200)
        self.client.set_cookie("aw_access", "expired")
        response = self.client.delete("/auth/session", headers=self.origin)
        self.assertEqual(response.status_code, 200)
        self.assertIn("aw_access=;", response.headers["Set-Cookie"])
        self.assertEqual(CountingGateway.validations, 0)

    def test_untrusted_forwarding_does_not_bypass_ip_limit(self):
        for i in range(31):
            response = self.client.get(
                "/auth/config", headers={"X-Forwarded-For": f"192.0.2.{i + 1}"}
            )
        self.assertEqual(response.status_code, 429)

    def test_trusted_chain_ignores_attacker_prefix_and_rejects_invalid_addresses(self):
        app = self.make_app(
            {
                "RATE_LIMIT_ENVIRONMENT": "testing",
                "RATE_LIMIT_TRUSTED_PROXY_CIDRS": "10.0.0.0/24",
            }
        )
        client = app.test_client()
        for i in range(31):
            response = client.get(
                "/auth/config",
                headers={"X-Forwarded-For": f"192.0.2.{i + 1}, 198.51.100.1, 10.0.0.2"},
                environ_overrides={"REMOTE_ADDR": "10.0.0.1"},
            )
        self.assertEqual(response.status_code, 429)
        limiter = app.extensions["auth_limiter"]
        with app.test_request_context(
            "/",
            headers={"X-Forwarded-For": "nonsense"},
            environ_base={"REMOTE_ADDR": "10.0.0.1"},
        ):
            self.assertEqual(limiter._key_func(), "10.0.0.1")

    def test_user_quota_follows_verified_account_across_ips(self):
        self.client.set_cookie("aw_access", "approved")
        with patch.dict(USER_LIMITS, {("auth_status", "GET"): "2 per minute"}):
            for address in ("192.0.2.1", "192.0.2.2"):
                self.assertEqual(
                    self.client.get(
                        "/auth/status", environ_overrides={"REMOTE_ADDR": address}
                    ).status_code,
                    200,
                )
            calls = len(FakeGateway.calls)
            response = self.client.get(
                "/auth/status", environ_overrides={"REMOTE_ADDR": "192.0.2.3"}
            )
            self.assertEqual(response.status_code, 429)
            self.assertGreater(int(response.headers["Retry-After"]), 0)
            self.assertEqual(len(FakeGateway.calls), calls)
            self.client.set_cookie("aw_access", "tampered")
            self.assertEqual(self.client.get("/auth/status").status_code, 401)

    def test_users_sharing_ip_have_separate_user_quotas(self):
        class OtherUser(CountingGateway):
            def user(self):
                user = super().user()
                user["id"] = self.token
                return user

        self.app.extensions["supabase_gateway_factory"] = OtherUser
        with patch.dict(USER_LIMITS, {("auth_status", "GET"): "1 per minute"}):
            self.client.set_cookie("aw_access", "first-user")
            self.assertEqual(self.client.get("/auth/status").status_code, 200)
            self.assertEqual(self.client.get("/auth/status").status_code, 429)
            self.client.set_cookie("aw_access", "second-user")
            self.assertEqual(self.client.get("/auth/status").status_code, 200)

    def test_reset_and_expiry_without_sleep(self):
        # Exercise the actual configured limit and storage expiry with a fake clock.
        clock = 10000000000.0
        with patch("time.time", return_value=clock):
            for _ in range(31):
                response = self.client.get("/auth/config")
            self.assertEqual(response.status_code, 429)
        with patch("time.time", return_value=clock + 61):
            self.assertEqual(self.client.get("/auth/config").status_code, 200)
        self.limiter.reset()
        self.assertEqual(self.client.get("/auth/config").status_code, 200)

    def test_dash_callbacks_and_assets_have_no_auth_quota(self):
        @self.app.post("/_dash-update-component")
        def callback():
            return {"ok": True}

        self.client.set_cookie("aw_access", "approved")
        for _ in range(65):
            self.assertEqual(
                self.client.post(
                    "/_dash-update-component", headers=self.origin
                ).status_code,
                200,
            )
        self.assertEqual(self.client.get("/auth/config").status_code, 200)

    def test_auth_guards_still_fail_closed(self):
        response = self.client.post("/auth/session", json={"access_token": "approved"})
        self.assertEqual(response.status_code, 403)
        for token, status in (("tampered", 401), ("unconfirmed", 403), ("outage", 503)):
            response = self.client.post(
                "/auth/session", json={"access_token": token}, headers=self.origin
            )
            self.assertEqual(response.status_code, status)
            self.assertNotIn("aw_access=", response.headers.get("Set-Cookie", ""))
        response = self.client.post(
            "/auth/session", json={"access_token": "no-member"}, headers=self.origin
        )
        self.assertFalse(response.json["approved"])
        self.assertIn("aw_access=;", response.headers["Set-Cookie"])

    def test_runtime_storage_failure_is_sanitized_503_before_supabase(self):
        with patch.object(
            self.limiter.storage, "incr", side_effect=RedisConnectionError("secret-url")
        ):
            response = self.client.get("/auth/registration")
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.is_json)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertNotIn("secret-url", response.get_data(as_text=True))
        self.assertFalse(FakeGateway.calls)

    def test_header_storage_failure_returns_503(self):
        with patch.object(
            self.limiter.storage, "get", side_effect=RedisConnectionError("secret-url")
        ):
            response = self.client.get("/auth/config")
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.is_json)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    def test_production_requires_shared_storage(self):
        for env in (
            {},
            {"RATE_LIMIT_ENVIRONMENT": "production"},
            {"RATE_LIMIT_ENVIRONMENT": "invalid"},
            {
                "RATE_LIMIT_ENVIRONMENT": "production",
                "RATE_LIMIT_REDIS_URL": "memory://",
            },
            {"RATE_LIMIT_ENVIRONMENT": "testing", "RATE_LIMIT_TRUST_PROXY": "1"},
            {
                "RATE_LIMIT_ENVIRONMENT": "testing",
                "RATE_LIMIT_TRUSTED_PROXY_CIDRS": "0.0.0.0/0",
            },
        ):
            with self.subTest(env=env), self.assertRaises(RuntimeError):
                self.make_app(env)

    def test_unavailable_redis_startup_does_not_leak_credentials(self):
        with patch(
            "redis.Redis.from_url", side_effect=RedisConnectionError("secret-url")
        ):
            with self.assertRaisesRegex(
                RuntimeError, "storage is unavailable"
            ) as error:
                self.make_app(
                    {"RATE_LIMIT_REDIS_URL": "redis://user:secret@localhost:6379/0"}
                )
        self.assertNotIn("secret", str(error.exception))

    def test_production_redis_backend_with_mocked_connectivity(self):
        with patch("redis.Redis.from_url") as connect:
            app = self.make_app({"RATE_LIMIT_REDIS_URL": "redis://localhost:6379/0"})
        connect.return_value.__enter__.return_value.ping.assert_called_once()
        self.assertEqual(
            type(app.extensions["auth_limiter"].storage).__name__, "RedisStorage"
        )

    def test_hourly_quota_and_expiry(self):
        start = 10000000000.0
        for i in range(101):
            with patch("time.time", return_value=start + (i // 25) * 61):
                response = self.client.get("/auth/config")
        self.assertEqual(response.status_code, 429)
        with patch("time.time", return_value=start + 3601):
            self.assertEqual(self.client.get("/auth/config").status_code, 200)

    def test_account_get_and_head_share_quota(self):
        self.client.set_cookie("aw_access", "approved")
        with patch.dict(USER_LIMITS, {("auth_status", "GET"): "1 per minute"}):
            self.assertEqual(self.client.get("/auth/status").status_code, 200)
            response = self.client.head(
                "/auth/status", environ_overrides={"REMOTE_ADDR": "192.0.2.10"}
            )
            self.assertEqual(response.status_code, 429)
            self.assertIn("Retry-After", response.headers)

    def test_two_production_instances_share_counter_keys(self):
        # Emulate Redis atomic counters offline while retaining RedisStorage and
        # the real limiter strategy/key construction in two independent apps.
        shared = MemoryStorage()
        with (
            patch("redis.Redis.from_url"),
            patch("limits.storage.redis.RedisStorage.incr", side_effect=shared.incr),
            patch("limits.storage.redis.RedisStorage.get", side_effect=shared.get),
            patch(
                "limits.storage.redis.RedisStorage.get_expiry",
                side_effect=shared.get_expiry,
            ),
        ):
            first = self.make_app(
                {"RATE_LIMIT_REDIS_URL": "redis://localhost:6379/0"}
            ).test_client()
            second = self.make_app(
                {"RATE_LIMIT_REDIS_URL": "redis://localhost:6379/0"}
            ).test_client()
            for _ in range(15):
                self.assertEqual(first.get("/auth/config").status_code, 200)
                self.assertEqual(second.get("/auth/config").status_code, 200)
            self.assertEqual(second.get("/auth/config").status_code, 429)
