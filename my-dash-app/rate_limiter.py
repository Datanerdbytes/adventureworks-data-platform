"""Auth-only limits with shared production storage and verified user keys."""

import math
import os
import time
from ipaddress import ip_address, ip_network
from urllib.parse import urlsplit

from flask import abort, jsonify, request
from flask_limiter import Limiter
from flask_limiter.errors import RateLimitExceeded
from limits import parse_many
from limits.errors import StorageError
from redis.exceptions import RedisError

# These quotas supplement the IP checks after Supabase verifies the account.
USER_LIMITS = {
    ("auth_session", "POST"): "60 per minute; 300 per hour",
    ("auth_status", "GET"): "120 per minute; 600 per hour",
    ("select_workspace", "POST"): "30 per minute; 100 per hour",
}


def _client_ip(trusted_proxies):
    """Walk forwarding addresses from the trusted peer toward the client.

    The proxy must append the actual sender to X-Forwarded-For. A client prefix
    cannot override the first untrusted address encountered from the right.
    """
    try:
        peer = ip_address(request.remote_addr)
    except (TypeError, ValueError):
        return "unknown-peer"
    if not any(peer in network for network in trusted_proxies):
        return str(peer)
    forwarded = request.headers.get("X-Forwarded-For", "")
    if not forwarded or len(forwarded) > 2048:
        return str(peer)
    try:
        addresses = [ip_address(value.strip()) for value in forwarded.split(",")]
    except ValueError:
        return str(peer)
    for address in reversed(addresses):
        if not any(address in network for network in trusted_proxies):
            return str(address)
    return str(peer)


def init_limiter(app):
    """Require Redis unless local development/testing is explicitly selected."""
    mode = os.environ.get("RATE_LIMIT_ENVIRONMENT", "production")
    if mode not in {"production", "development", "testing"}:
        raise RuntimeError("Invalid RATE_LIMIT_ENVIRONMENT configuration")
    if os.environ.get("RATE_LIMIT_TRUST_PROXY") == "1":
        raise RuntimeError(
            "Use RATE_LIMIT_TRUSTED_PROXY_CIDRS instead of blanket proxy trust"
        )
    try:
        trusted_proxies = tuple(
            ip_network(value.strip(), strict=True)
            for value in os.environ.get("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "").split(",")
            if value.strip()
        )
        if any(network.prefixlen == 0 for network in trusted_proxies):
            raise ValueError("Cannot trust every address")
    except ValueError:
        raise RuntimeError("Invalid trusted proxy CIDR configuration") from None
    storage_uri = os.environ.get("RATE_LIMIT_REDIS_URL")
    if not storage_uri and mode == "production":
        raise RuntimeError(
            "Production auth rate limiting requires RATE_LIMIT_REDIS_URL"
        )
    storage_options = {}
    if storage_uri:
        if urlsplit(storage_uri).scheme not in {"redis", "rediss"}:
            raise RuntimeError("RATE_LIMIT_REDIS_URL must use redis:// or rediss://")
        storage_options = {"socket_connect_timeout": 2, "socket_timeout": 2}
        import redis

        try:
            with redis.Redis.from_url(storage_uri, **storage_options) as client:
                client.ping()
        except Exception:
            # Never include an exception containing a credential-bearing URL.
            raise RuntimeError("Auth rate-limit storage is unavailable") from None
    limiter = Limiter(
        app=app,
        key_func=lambda: _client_ip(trusted_proxies),
        storage_uri=storage_uri or "memory://",
        storage_options=storage_options,
        default_limits=[],
        headers_enabled=False,
        swallow_errors=False,
        in_memory_fallback_enabled=False,
        key_prefix="adventureworks-auth",
    )
    app.extensions["auth_limiter"] = limiter

    @app.errorhandler(RateLimitExceeded)
    def throttled(error):
        response = jsonify(error="Too many requests. Please wait before trying again.")
        response.status_code = 429
        return response

    def unavailable(error):
        response = jsonify(
            error="Authentication is temporarily unavailable. Please try again later."
        )
        response.status_code = 503
        response.headers["Retry-After"] = "30"
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.after_request
    def rate_headers(response):
        if response.status_code == 503:
            return response
        current = limiter.current_limit
        if current is None:
            return response
        try:
            reset = current.reset_at
            response.headers["X-RateLimit-Limit"] = str(current.limit.amount)
            response.headers["X-RateLimit-Remaining"] = str(current.remaining)
            response.headers["X-RateLimit-Reset"] = str(reset)
            if response.status_code == 429 and "Retry-After" not in response.headers:
                response.headers["Retry-After"] = str(
                    max(1, math.ceil(reset - time.time()))
                )
        except (RedisError, StorageError):
            response = unavailable(None)
        return response

    app.register_error_handler(RedisError, unavailable)
    app.register_error_handler(StorageError, unavailable)
    return limiter


def enforce_user_limit(limiter, user):
    """Count only a server-verified identity, before membership/RPC work."""
    method = "GET" if request.method == "HEAD" else request.method
    policy = USER_LIMITS.get((request.endpoint, method))
    if policy is None:
        return
    user_id = user.get("id")
    if not isinstance(user_id, str) or not user_id:
        response = jsonify(error="Authentication is temporarily unavailable.")
        response.status_code = 503
        abort(response)
    for limit in parse_many(policy):
        identifiers = ("adventureworks-auth-user", request.endpoint, method, user_id)
        if not limiter.limiter.hit(limit, *identifiers):
            reset, _ = limiter.limiter.get_window_stats(limit, *identifiers)
            response = jsonify(
                error="Too many requests. Please wait before trying again."
            )
            response.status_code = 429
            response.headers["Retry-After"] = str(
                max(1, math.ceil(reset - time.time()))
            )
            abort(response)
