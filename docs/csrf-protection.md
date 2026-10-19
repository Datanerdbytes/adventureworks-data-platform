> Authentication cutover prepared 2026-10-19: the current owner/admin account model is documented in [Account management](account-management.md). Workspace approval, switching, and workspace bootstrap instructions below describe the retired model. Hosted rollout is a separate operator step.

# Browser mutation CSRF protection

Cookie-authenticated application mutations require both the exact configured
`Origin` and an `X-CSRF-Token` header. This includes `/auth/session` POST and
DELETE before login, `/auth/workspace` POST, and every Dash callback POST,
including read callbacks and workspace governance mutations. Authorization,
confirmed identity, current membership, role checks and database RLS still apply.
Invalid tokens return 403 before mutation callbacks or external RPCs execute.
Anonymous protected requests continue to return 401.

The browser obtains a token from GET `/auth/csrf` with `X-CSRF-Request: 1`.
This endpoint rejects cross-site fetch metadata and any supplied foreign Origin.
The custom header prevents a cross-origin simple request; no CORS access is
provided. Issuance has an independent IP quota of 600 per minute and 12,000
per hour; it never consumes the session synchronization quota. Responses are
private/no-store. `/auth/config` remains public project
configuration only.

The endpoint issues a separate random 256-bit nonce in a signed, HttpOnly,
SameSite=Lax browser-session cookie named `aw_csrf`. It uses Secure with the same
HTTPS/local-development policy as authentication cookies, a dedicated signature
salt, SHA-256, and a maximum signed age of 24 hours. Flask's signed session still
contains only the selected workspace ID. No CSRF state enters `dcc.Store`.
The submitted token is an HMAC of this nonce and a digest of the current access
cookie, using the server secret. A cookie signature is checked before constant-time
header comparison. Thus another browser's token, a forged nonce cookie, or a token
issued before an access-cookie change cannot authorize a mutation. The security
cookie contains no access token. Missing, malformed or expired security cookies
are renewed only by the issuance endpoint.

The frontend fetch wrapper installs before session synchronization or Dash renderer
startup. It retrieves a current token before each application mutation, serializes
issuance and dispatch within a tab while allowing concurrent callback execution, preserves Request/Headers/body/signal semantics,
and forbids redirects for protected writes. It attaches tokens only to same-origin
`/auth/session`, `/auth/workspace`, and `/_dash-update-component`; Supabase requests
and other destinations are untouched. New mutation routes must be added to this
frontend allowlist; backend protection applies to all unsafe protected requests.
No XMLHttpRequest hook is needed: the application and Dash renderer use fetch.

Login and refreshed access cookies change the effective token. Successful logout
and unapproved sign-in clear the nonce cookie. Other tabs retrieve the current
cookie-bound token on their next mutation. A concurrent auth-cookie change in a
different tab can race between issuance and submission; rejection fails closed
and requires a deliberate retry/reload. Rejected writes are never automatically
replayed. Read-only GETs require no CSRF token. Startup issuance failures keep the
existing authentication failure/loading behavior and do not release Dash requests.

Offline backend tests exercise actual Dash governance callback requests and assert
that rejected mutations do not reach RPCs. Frontend tests cover token acquisition,
Request and header overrides, destination isolation, cancellation, concurrent
issuance, lifecycle changes and absence of replay.
