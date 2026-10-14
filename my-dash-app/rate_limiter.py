"""Flask-Limiter configuration with Redis backend for production, memory for local dev/tests."""

import os
from functools import wraps
from typing import Optional, Callable

from flask import Flask, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def _get_redis_url() -> Optional[str]:
    """Get Redis URL from environment for production rate limiting."""
    redis_url = os.environ.get("RATE_LIMIT_REDIS_URL")
    if redis_url:
        return redis_url
    return None


def _get_client_ip() -> str:
    """Get client IP address without trusting X-Forwarded-For blindly."""
    # Only trust X-Forwarded-For if behind a known proxy (set by deployment)
    if os.environ.get("RATE_LIMIT_TRUST_PROXY") == "1":
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return get_remote_address()


def _get_user_key() -> str:
    """Get user identifier for authenticated rate limiting.
    
    Returns a user-scoped key only after server-verified identity.
    For unauthenticated requests, falls back to IP.
    """
    # Check if we have a verified user in Flask g
    if hasattr(request, "g") and hasattr(request.g, "auth_user"):
        user = request.g.auth_user
        if isinstance(user, dict) and user.get("id"):
            return f"user:{user['id']}"
    # Fall back to IP for unauthenticated requests
    return f"ip:{_get_client_ip()}"


def init_limiter(app: Flask) -> Limiter:
    """Initialize Flask-Limiter with appropriate storage backend.
    
    Production: Redis (requires RATE_LIMIT_REDIS_URL env var)
    Local dev/tests: In-memory storage
    
    Raises:
        RuntimeError: If Redis is configured but unavailable
    """
    redis_url = _get_redis_url()
    
    if redis_url:
        # Production: Use Redis backend
        try:
            import redis
            redis_client = redis.from_url(redis_url, decode_responses=True)
            # Test connection
            redis_client.ping()
            storage_uri = redis_url
        except Exception as e:
            raise RuntimeError(f"Redis backend configured but unavailable: {e}")
    else:
        # Local dev/tests: Use in-memory storage
        storage_uri = "memory://"
    
    limiter = Limiter(
        app=app,
        key_func=_get_client_ip,
        storage_uri=storage_uri,
        default_limits=["200 per day", "50 per hour"],
        headers_enabled=True,
    )
    
    # Add user-scoped key function for authenticated endpoints
    limiter._user_key_func = _get_user_key
    
    # Store in Flask extensions for retrieval
    app.extensions["limiter"] = limiter
    
    return limiter


def get_limiter() -> Optional[Limiter]:
    """Get the limiter instance from Flask extensions."""
    from flask import current_app
    return current_app.extensions.get("limiter")


def limit_ip(limits: list, methods: Optional[list] = None):
    """Decorator to apply IP-based rate limit to specific endpoint."""
    def decorator(f: Callable) -> Callable:
        limiter = get_limiter()
        if limiter:
            return limiter.limit(limits, methods=methods, key_func=_get_client_ip)(f)
        return f
    return decorator


def limit_user(limits: list, methods: Optional[list] = None):
    """Decorator to apply user-based rate limit to specific endpoint.
    
    Falls back to IP for unauthenticated requests.
    """
    def decorator(f: Callable) -> Callable:
        limiter = get_limiter()
        if limiter:
            return limiter.limit(limits, methods=methods, key_func=_get_user_key)(f)
        return f
    return decorator