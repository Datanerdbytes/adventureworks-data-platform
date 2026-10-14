# Authentication rate limits

The auth limiter requires `flask-limiter[redis]==3.12`, supplied by the Phase 2
dependency branch. Integrate its manifest and lockfile changes before a frozen
install or Docker build of this branch.

## Storage and environments

`RATE_LIMIT_ENVIRONMENT` defaults to `production`. Production startup requires
`RATE_LIMIT_REDIS_URL` using `redis://` or `rediss://` and checks connectivity with
two-second connect/read timeouts. All workers and instances must use the same
Redis database. Supply credential-bearing URLs through the deployment secret
configuration; never commit or log them.

Set `RATE_LIMIT_ENVIRONMENT=development` explicitly for local memory storage, or
`RATE_LIMIT_ENVIRONMENT=testing` for offline tests. Memory counters are local to
each process and reset on restart. These modes must not be used in production.

Missing production storage or failed startup connectivity stops startup. Runtime
storage failures return a sanitized JSON 503 and `Retry-After: 30`; requests fail
closed rather than falling back to memory. No requests are automatically replayed.

## Client addresses behind proxies

Forwarding headers are ignored by default. Where a reverse proxy is required,
configure `RATE_LIMIT_TRUSTED_PROXY_CIDRS` with the specific peer/proxy networks
under your control, separated by commas. The proxy must overwrite or append the
actual sender to `X-Forwarded-For`, and untrusted clients must not be able to reach
the application from a trusted peer address. Do not use a universal network or
trust all private addresses merely because the application is hosted behind a
proxy. Verify the actual deployment topology before configuring these networks.

The limiter walks the chain from the right, beginning with the trusted immediate
peer, and stops at the first untrusted address. Client-supplied prefixes cannot
change that address. Invalid/oversized forwarding headers use the peer address.
The old blanket `RATE_LIMIT_TRUST_PROXY=1` setting is rejected at startup.

## Policies

All limits below apply per endpoint. Session POST and DELETE have separate quotas.
HEAD requests on read-only endpoints share the GET IP quota.

| Endpoint                                            | IP limits            | Verified account limits |
| --------------------------------------------------- | -------------------- | ----------------------- |
| GET `/auth/config`                                  | 30/minute, 100/hour  | —                       |
| GET `/auth/registration`                            | 20/minute, 60/hour   | —                       |
| POST `/auth/session`                                | 30/minute, 300/hour  | 60/minute, 300/hour     |
| DELETE `/auth/session`                              | 120/minute, 600/hour | —                       |
| GET `/auth/status`                                  | 120/minute, 600/hour | 120/minute, 600/hour    |
| POST `/auth/workspace`                              | 30/minute, 100/hour  | 30/minute, 100/hour     |
| Login/signup/callback/recovery/access-pending pages | 20/minute, 60/hour   | —                       |

IP limits run before Supabase validation. Account limits use the identity returned
by server-side Supabase verification and run before membership/RPC work. They do
not use browser claims or raw tokens. Logout clears cookies without requiring a
valid token, so an expired session can still be cleared. DASH callbacks and assets
have no default auth quota; the existing server authorization guard still applies.

Throttled requests return JSON 429 with a human-readable `error`, `Retry-After`,
and `Cache-Control: private, no-store`. Successful limited requests include
`X-RateLimit-*` headers for the IP quota. Account throttling supplies its own
retry interval. Fixed windows provide bounded cooldowns without blocking sleeps.
These application quotas supplement Supabase's password lockout/provider limits.
Shared NAT users share an IP quota; monitor actual usage before tuning quotas.

## Offline verification

```sh
RATE_LIMIT_ENVIRONMENT=testing .venv/bin/python -B -m unittest discover -s tests -v
npm run test:auth
```

Tests create fresh limiters or reset in-memory state between cases. Redis startup
and outage paths are mocked; no production Redis, Supabase, or BigQuery calls are
made. Deployment Redis connectivity and proxy topology still need operational
verification before rollout.
