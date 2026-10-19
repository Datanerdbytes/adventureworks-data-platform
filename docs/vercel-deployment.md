# Vercel deployment

`vercel.json` explicitly selects `Dockerfile.vercel` as the dashboard container
service and routes requests to it. Its build stages mirror `Dockerfile`; keep both
files aligned. The Vercel-specific startup helper loads runtime Google credentials.
The routing port matches the server's port, 8050. Authentication and Dash asset
requests remain under the Flask request guard. Container services are a Vercel beta.

Before deploying, verify the linked owner/project with
`vercel project inspect --non-interactive`. This checkout does not choose a project
implicitly. Use `vercel link` only after selecting the intended account and project.

Configure server-side runtime values on the selected project:

- The existing Supabase public URL/key and server-only service-role key.
- A stable `FLASK_SECRET_KEY` and the exact HTTPS `AUTH_APP_ORIGIN` of the deployed
  application. Allow its callback and recovery URLs in Supabase.
- `RATE_LIMIT_ENVIRONMENT=production` and a reachable Redis connection in
  `RATE_LIMIT_REDIS_URL`. Never substitute process-local development limiting.
- BigQuery project/dataset settings and production Google credentials. Local ADC
  and local credential file paths do not automatically work in Vercel. Store the
  service-account JSON as the server-side `GOOGLE_CREDENTIALS_JSON` secret. The
  container startup helper materializes it in a private temporary file and removes
  the JSON from the environment before starting workers.
- Keep password lockout disabled until its coordinated migration/hook rollout is
  complete; see [account management](account-management.md).

`.vercelignore` excludes local secrets, credentials, environments and unrelated
pipeline artifacts from uploads. `.vercel/` is ignored by Git. Supply runtime
credentials separately; do not copy `.env` or Google keys into the container image.

Deploy a preview using `vercel deploy`, inspect the build with `vercel inspect`,
and verify public landing/login routes, denied anonymous Dash requests, CSRF,
verified sign-in and warehouse reports before a production release. Container
functions scale independently, so the temporary warehouse cache is instance-local;
Redis remains the shared authentication limiter. Deployment does not apply SQL
migrations or change Supabase provider/redirect settings automatically.

## Deployment record — 2026-10-20

- Project: `datanerdbytes-4121/adventureworks-analytics`.
- Production: <https://adventureworks-analytics-snowy.vercel.app>.
- Deployment: `dpl_9L34a6hBbZ9Po1UfvJoA588VwTgL`, container build READY.
- Upstash resource: `adventureworks-auth-limits`, free plan, automatic upgrades
  disabled, TLS connection verified. Production uses shared Redis rate limiting.
- Production-only Supabase/Google credentials and a fresh Flask secret were
  configured with explicit user authorization. Credential values are not recorded.
- Set `AUTH_OAUTH_PROVIDERS=google,github` in production. Both providers were
  verified enabled through Supabase's public Auth settings. An empty value hides
  both OAuth buttons; preserve the existing provider selection when redeploying.
- Live checks: landing/login/config HTTP 200; anonymous Dash layout HTTP 401;
  login startup completes in the browser; no error records in the queried runtime
  log window. The offline Python suite passed 246 tests.
- Full authenticated reports and signup/recovery email redirects were not tested.
  Supabase URL Configuration was subsequently updated and verified in the dashboard:
  Site URL is the production origin; redirects allow `/auth/callback`,
  `/auth/callback?**` (the app's next/registration query parameters), and
  `/auth/recovery?step=update`. The existing local recovery entry was retained.
  Start a new OAuth attempt after changing these settings; an already-issued link
  pointing at localhost does not update automatically. No hosted SQL migration was
  run during deployment.
