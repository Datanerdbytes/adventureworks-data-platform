"""Canonical filesystem memoization and bounded, process-safe warehouse misses."""

from contextlib import contextmanager
import fcntl
from functools import wraps
import hashlib
import inspect
import json
import math
import os
import time

from flask import current_app

LOCK_STRIPES = 64


def positive_threshold(value):
    """Validate an entry budget without truncating fractional input."""
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit():
        raise ValueError("KPI_CACHE_THRESHOLD must be a positive integer")
    result = int(value)
    if result <= 0:
        raise ValueError("KPI_CACHE_THRESHOLD must be a positive integer")
    return result


def positive_lock_timeout(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            "KPI_CACHE_LOCK_TIMEOUT_SECONDS must be finite and positive"
        ) from None
    if not math.isfinite(result) or result <= 0:
        raise ValueError("KPI_CACHE_LOCK_TIMEOUT_SECONDS must be finite and positive")
    return result


def lock_stripe(key):
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % LOCK_STRIPES


@contextmanager
def query_lock(key):
    directory = current_app.extensions["executive_query_lock_dir"]
    timeout = current_app.config.get("KPI_CACHE_LOCK_TIMEOUT_SECONDS", 30.0)
    path = directory / f"query-{lock_stripe(key)}.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        "Timed out waiting for warehouse cache load"
                    ) from None
                time.sleep(min(0.05, remaining))
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def warehouse_memoize(cache, *, timeout=60, coalesce=True):
    """Share one stable key for lookup and locking, without version-key races.

    Tuple envelopes distinguish cached None in one lookup. Only direct warehouse
    functions lock; derived memoized functions cannot hold a stripe across calls
    to direct loaders. Warehouse exceptions propagate and are never cached.
    """

    def decorate(function):
        signature = inspect.signature(function)

        def make_cache_key(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            identity = json.dumps(
                [
                    function.__module__,
                    function.__qualname__,
                    list(bound.arguments.items()),
                ],
                ensure_ascii=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            return "warehouse-v1:" + hashlib.sha256(identity.encode()).hexdigest()

        def read_or_load(key, args, kwargs):
            entry = cache.get(key)
            if entry is not None:
                return entry[0]
            value = function(*args, **kwargs)
            cache.set(key, (value,), timeout=timeout)
            return value

        @wraps(function)
        def wrapped(*args, **kwargs):
            key = make_cache_key(*args, **kwargs)
            entry = cache.get(key)
            if entry is not None:
                return entry[0]
            if not coalesce:
                return read_or_load(key, args, kwargs)
            with query_lock(key):
                return read_or_load(key, args, kwargs)

        setattr(wrapped, "uncached", function)
        setattr(wrapped, "make_cache_key", make_cache_key)
        setattr(wrapped, "cache_timeout", timeout)
        return wrapped

    return decorate
