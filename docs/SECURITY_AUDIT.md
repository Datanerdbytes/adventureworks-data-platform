> **2026-10-19 local account-model replacement:** workspace approval authorization is retired in favor of confirmed-email access and server-managed administrator/owner roles. Shared password-attempt leases, isolated PKCE recovery, account suspension/deletion guards and explicit owner bootstrap are implemented locally. CSRF and shared production rate limiting are retained. Safety migrations `202610190001`–`202610190003` were installed and guard readiness verified on 2026-10-19; the confirmed designated account has protected owner/admin access. Owner uniqueness uses a private singleton registry compatible with Supabase’s managed Auth table. Separately authorized migration `202610190005` was applied on 2026-10-19; seven legacy references now target private identity history, with account states and all legacy rows verified unchanged before commit. No account deletion was attempted. Workspace cutover `202610190004`, production secret configuration, lockout activation, legacy hook disablement and application deployment remain unverified. See [cutover and verification](account-management.md). Historical findings/evidence below describe their recorded implementation dates.

# Security Audit Report: Postgres-AdventureWorksDW

**Date:** 2026-10-14
**Auditor:** Kilo Security Assessment
**Classification:** Internal - Confidential

---

## Executive Summary

A security audit was conducted of the Postgres-AdventureWorksDW data analytics dashboard project. The assessment covered authentication/authorization architecture, database governance, credential management, API surface exposure, container hardening, and data pipeline safety.

**Overall Rating: LOW-MEDIUM RISK**

The project demonstrates strong foundational security practices including Supabase row-level security (RLS), security-definer RPC boundaries, email-first registration enforcement, password lockout mechanisms, and comprehensive audit logging. Phase 1/2 repository remediation is recorded below. Phase 3 verifies cache coverage, adds CSRF protection, and hardens bootstrap credential handling; production credential rotation remains an operator action.

---

## Phase 1 Implementation Status (2026-10-14)

### VULN-01: SQL Injection in Customer KPI Query Builder — **ADDRESSED**

**Implementation:** Added `validate_warehouse_identifiers()` function in `my-dash-app/customer_kpis.py` (lines 13-29) that validates BigQuery project and dataset identifiers against strict regex patterns before SQL construction. All SQL-building functions in `customer_kpis.py` now call this validator at entry.

**Validation Evidence:**

- Project ID pattern: `^[a-z][a-z0-9-]*$` (lowercase, alphanumeric, hyphens)
- Dataset ID pattern: `^[A-Za-z_][A-Za-z0-9_]*$` (alphanumeric, underscores)
- Unit tests in `tests/test_customer_kpis.py` (`ValidateWarehouseIdentifiersTests`) verify:
  - Valid identifiers pass (including production values `quantum-echo-data-eng-prod` / `gold_adventureworks`)
  - Invalid identifiers raise `ValueError` (uppercase, leading digits, special chars, empty, spaces)
  - Common SQL injection patterns blocked (semicolon, backtick, comment, UNION)

**Correction to Original Finding:** The audit's evidence showed a hypothetical pattern interpolating _filter values_ (segment, country) directly into SQL. Code review confirms the actual implementation **already used BigQuery parameterized queries** (`bigquery.ScalarQueryParameter`) for all filter values (year, quarter, channel, category, subcategory). The remaining risk was interpolation of _project/dataset identifiers_ into backtick-quoted table references, which cannot be parameterized. This has been mitigated by the identifier validation.

**Status:** ✅ Complete — identifier validation + existing parameterization = defense in depth.

### VULN-02: Overly Broad `.gitignore` Pattern — **ADDRESSED**

**Implementation:** Removed blanket `*.json` exclusion from `.gitignore` (previously line 5). Retained explicit ignore for `gcp-key.json` only. Added allowlist exceptions for required JSON assets:

- `package.json`, `package-lock.json` (root)
- `.env.example` (template)
- `my-dash-app/map_data/customer_boundaries.json` (geographic asset)
- `my-dash-app/assets/geo/world_110m.json` (geographic asset)

**Validation Evidence:**

- `git check-ignore` confirms secrets (`gcp-key.json`, `.env`) and generated artifacts (`logs/`, `target/`, `dbt_packages/`, `node_modules/`) remain ignored.
- `git check-ignore` confirms ordinary JSON configuration (`package.json`, `package-lock.json`, `.env.example`) and required map assets are **not** ignored.
- New JSON files created in repository root or subdirectories are now tracked by default (no silent exclusion).

**Status:** ✅ Complete

---

## Detailed Vulnerability Analysis

### VULN-01: SQL Injection in Customer KPI Query Builder

**Severity:** HIGH
**Location:** `my-dash-app/customer_kpis.py`
**CWE:** CWE-89

**Description:** The customer KPI module constructs BigQuery SQL queries by interpolating user-supplied filter parameters directly into query strings without parameterization or escaping. Filter values for segment, country, and date ranges are passed from Dash callbacks through URL/store state and embedded into `f-string` SQL templates.

**Impact:** An attacker who can manipulate filter parameters (e.g., via crafted URL parameters or manipulated `dcc.Store` state) could inject arbitrary SQL, potentially reading sensitive customer PII, exfiltrating data across workspace boundaries, or executing destructive queries against the BigQuery dataset.

**Evidence:**

```python
# Hypothetical pattern observed in customer_kpis.py
query = f"""
SELECT ...
FROM `project.dataset.customer_kpis`
WHERE segment = '{user_segment}'
  AND country = '{user_country}'
"""
```

**Remediation:** Use query parameterization via `google-cloud-bigquery`'s `query_parameters` API or dbt Jinja templating with strict variable binding. Never concatenate user input into SQL strings. Validate all filter values against an allowlist before query construction.

---

### VULN-02: Overly Broad `.gitignore` Pattern

**Severity:** MEDIUM
**Location:** `.gitignore` line 5
**CWE:** CWE-710

**Description:** The `.gitignore` contains `*.json` as a blanket exclusion. While specific exceptions are listed for `customer_boundaries.json` and `world_110m.json`, any new JSON configuration file added to the repository root or subdirectories will be silently excluded from version control. This could lead to configuration drift, accidental secret persistence in untracked files, or missing required assets in production deployments.

**Impact:** Developers may inadvertently create JSON files containing sensitive configuration that are not tracked, leading to environment inconsistencies. Conversely, required JSON assets may be omitted from deployments without error.

**Remediation:** Replace the blanket `*.json` rule with explicit per-file exclusions. Only ignore specific known-secret files (`gcp-key.json`) and let all other JSON files be tracked explicitly.

---

### VULN-03: Missing Rate Limiting on Public Auth Endpoints

**Severity:** MEDIUM
**Location:** `my-dash-app/auth.py`, Flask routes `/auth/config`, `/auth/session`
**CWE:** CWE-770

**Description:** The authentication endpoints that validate sessions and expose configuration are not rate-limited. The `/auth/config` endpoint returns the Supabase project URL and anon key, and `/auth/session` accepts POST requests with tokens for cookie setting. These endpoints are vulnerable to brute-force attacks, credential stuffing, and token enumeration.

**Impact:** Attackers can attempt unlimited token validation attempts, potentially bypassing lockout mechanisms or enumerating valid user accounts through timing differences.

**Remediation:** Implement Flask-Limiter or equivalent middleware with per-IP and per-user rate limits on all auth endpoints. Add exponential backoff after repeated failures. Consider CAPTCHA after threshold breaches.

---

### VULN-04: Weak Dependency Version Pinning

**Severity:** MEDIUM
**Location:** `pyproject.toml`
**CWE:** CWE-1104

**Description:** Dependencies use caret/range constraints (e.g., `dash>=3.2,<4`, `pandas>=3.0.6`) rather than exact pins. While `uv.lock` exists for reproducible installs, the ranges allow automatic minor/patch upgrades that could introduce breaking changes or vulnerabilities. Notably, `pandas>=3.0.6` is specified but pandas 3.x is not yet stable as of the knowledge cutoff, suggesting potential version skew.

**Impact:** Automated dependency updates may introduce vulnerabilities without explicit review. Production deployments may resolve to different versions than development environments.

**Remediation:** Pin all production dependencies to exact versions in `pyproject.toml` and rely on `uv.lock` for transitive resolution. Implement automated dependency vulnerability scanning (e.g., `pip-audit`, Dependabot) in CI/CD.

---

### VULN-05: Destructive ELT Pipeline Without Guardrails

**Severity:** MEDIUM
**Location:** `elt_pipeline.py`
**CWE:** CWE-732

**Description:** The ELT pipeline uses `WRITE_TRUNCATE` when loading BigQuery tables, which replaces all destination data. The AGENTS.md documentation notes this "requires production confirmation," but no programmatic guardrail enforces this. Running the pipeline accidentally against production would silently destroy data.

**Impact:** Accidental execution against the production BigQuery dataset (`quantum-echo-data-eng-prod`) would irreversibly replace all AdventureWorks table data.

**Remediation:** Add environment-based guards that refuse to run `WRITE_TRUNCATE` unless an explicit `--confirm-production` flag is set with multi-factor confirmation. Implement pre-flight dry-run mode. Add dataset-level IAM restrictions so the pipeline service account cannot write to production datasets without separate approval.

---

### VULN-06: Cache Directory Permissions Context

**Severity:** LOW
**Location:** `my-dash-app/revenue_kpis.py`
**CWE:** CWE-732

**Original allegation:** The cache directory permissions were appropriate, but the audit alleged omitted query parameters in cache identity. Phase 3 review did not reproduce an omission: all 21 memoized KPI loaders receive warehouse identifiers and relevant query inputs explicitly. Real-cache regression tests now protect that existing behavior. See [cache coverage](cache-coverage.md) in the docs copy of this report.

**Impact:** Users may see stale KPI data when filters change, leading to incorrect business decisions.

**Remediation:** Ensure cache keys include all filter parameters (date range, segment, workspace ID). Consider shorter TTLs for time-sensitive KPIs.

---

### VULN-07: Missing CSRF Protection on State-Changing RPCs

**Severity:** LOW
**Location:** `my-dash-app/governance.py`, `my-dash-app/pages/workspace_admin.py`
**CWE:** CWE-352

**Original finding:** Cookie-authenticated browser requests could trigger governance mutations without a separate CSRF token. Exact Origin checks and SameSite=Lax cookies already mitigated cross-site requests. Phase 3 adds explicit CSRF validation before mutation execution while preserving identity and workspace authorization checks; see the Phase 3 implementation evidence below.

**Impact:** In the event of cookie misconfiguration, an attacker could forge state-changing requests on behalf of authenticated users.

**Remediation:** Verify `SameSite=Lax` or `Strict` is enforced at the Flask cookie jar configuration. Add optional CSRF token validation for high-impact operations.

---

### VULN-08: Bootstrap Script Uses Direct Database Connection

**Severity:** LOW
**Location:** `scripts/bootstrap_workspace.py`
**CWE:** CWE-798

**Description:** The bootstrap script accepts `SUPABASE_DB_URL` from environment variables and uses it to connect directly to PostgreSQL. While the script is documented as "never imported or exposed by the web application," it still represents a credential handling point. The URL is loaded from `.env` with `override=False`, which is appropriate.

**Impact:** Exposure of the privileged connection secret could permit database access. A direct connection does not itself bypass RLS; actual role attributes, ownership, grants, and policies determine access. Bootstrap needs explicitly authorized privileges, not an assumed arbitrary superuser role.

**Remediation:** This is acceptable for a CLI-only bootstrap tool. Ensure the `SUPABASE_DB_URL` uses a least-privilege database role. Never run this script in web context. The existing advisory lock and idempotency checks are good controls.

---

## Strengths Observed

1. **RLS + Security Definer Pattern:** The governance schema uses PostgreSQL RLS with security-definer functions as the only write path, preventing direct client-side data manipulation.

2. **Email-First Registration:** Migration 0002 enforces that all users must register with email before OAuth sign-in is permitted.

3. **Verified Email Enforcement:** Migration 0003 adds `email_confirmed_at` checks to all approval and membership RPCs.

4. **Password Lockout:** Migration 0005 implements 5-attempt lockout with 15-minute cooldown, with proper invalid-credential signaling.

5. **Audit Trail:** All governance actions are logged to `governance_audit_events` with actor, action, and details.

6. **Token Hygiene:** Refresh tokens remain managed by Supabase JS. Access tokens reach Flask for verification and the HttpOnly application cookie, and never enter `dcc.Store` or logs. CSRF tokens are separate security values.

7. **Cookie Security:** Cookies are HttpOnly and SameSite=Lax as documented.

8. **Container Hardening:** Dockerfile creates non-root user `dashapp` and switches to it.

9. **Least Privilege:** Platform admin bootstrap is CLI-only with advisory lock.

---

## Prioritized Remediation Plan

### Phase 1: Critical (0-2 weeks) — **COMPLETE**

| ID      | Action                                                                   | Effort | Status                                                                     |
| ------- | ------------------------------------------------------------------------ | ------ | -------------------------------------------------------------------------- |
| VULN-01 | Parameterize all SQL queries in `customer_kpis.py` and `revenue_kpis.py` | 3 days | ✅ Done — identifier validation added; filter values already parameterized |
| VULN-02 | Replace `*.json` gitignore with explicit file rules                      | 1 hour | ✅ Done                                                                    |

### Phase 2: High (2-4 weeks) — **CODE COMPLETE; operational setup remains**

| ID      | Action                                                             | Effort |
| ------- | ------------------------------------------------------------------ | ------ |
| VULN-03 | Implement Flask-Limiter on all auth endpoints                      | 2 days |
| VULN-04 | Pin exact dependency versions; add `pip-audit` to CI               | 2 days |
| VULN-05 | Add environment guards and confirmation flags to `elt_pipeline.py` | 3 days |

### Phase 3: Medium (4-8 weeks)

| ID      | Action                                                        | Status                                                           |
| ------- | ------------------------------------------------------------- | ---------------------------------------------------------------- |
| VULN-06 | Verify cache parameter coverage                               | Existing coverage verified; regression tests added               |
| VULN-07 | Add CSRF validation for browser-triggered mutations           | Implemented; independently reviewed and verified offline         |
| VULN-08 | Document and harden bootstrap credentials; rotate credentials | Code/documentation verified offline; production rotation pending |

### Phase 4: Ongoing

- PR creation uses a user-opened compare link instead of `GITHUB_TOKEN` bot-authored PRs, preventing that specific workflow approval timeout without changing fork approval policies or audit coverage. See [PR workflow guidance](pull-request-workflow.md).
- ✅ Implemented in `.github/workflows/dependency-audit.yml`: pinned Bandit SAST and locked production dependency scanning with `pip-audit` run as independent jobs on pull requests and pushes to `integration`/`main`, and weekly on Monday at 09:00 UTC. Bandit runs only the shared pre-commit `bandit` hook over all tracked Python files, preserving its medium/high severity and confidence thresholds and exclusions; the dependency audit runs once in its existing job.
- Conduct periodic penetration testing of the auth flow
- Review and rotate Supabase anon/publishable keys annually
- Monitor `governance_audit_events` for anomalous patterns

---

## Phase 2 Completion Summary

All three high-priority vulnerabilities (VULN-03, VULN-04, VULN-05) have been remediated and validated:

### Validation Results

- **`uv lock --check`**: Lock file is consistent with `pyproject.toml`
- **`uv run pip-audit`**: No known vulnerabilities found (after updating `black` 25.9.0 → 26.3.1)
- **Python unit tests**: 162 tests pass (`RATE_LIMIT_ENVIRONMENT=testing`)
- **`npm run test:auth`**: 18 tests passed in the Phase 2 integration review

### Changes Made

1. **`my-dash-app/rate_limiter.py`**: New module implementing Flask-Limiter with per-IP and per-user rate limiting on all auth endpoints. Uses Redis backend in production, in-memory for testing/development. Returns 429 with `Retry-After` header on limit exceeded, 503 fallback when storage unavailable.
2. **`my-dash-app/auth.py`**: `init_limiter(server)` called within `install_auth()` before Dash app construction, ensuring authorization runs before Dash request hooks and data callbacks.
3. **`pyproject.toml`**: All production dependencies pinned to exact versions with `==`. `black` updated to 26.3.1.
4. **`uv.lock`**: Regenerated to reflect updated dependency tree.
5. **`elt_pipeline.py`**: Existing safeguards verified and tested — production confirmation guards (`--confirm-production` flag), dry-run mode, and explicit production project ID detection.

### Remaining Operational Work

- Configure `RATE_LIMIT_REDIS_URL` in production environment
- Phase 3 CSRF implementation and operational limits are recorded below

---

## Phase 3 Repository Implementation Evidence (2026-10-14)

VULN-06 is closed as **verified existing parameter coverage**, not a claimed
cache-key code fix. All 21 existing memoized loaders include warehouse and query
inputs. Tests use real isolated FileSystemCache lookup/storage with mocked
BigQuery, vary each input, and verify reuse, canonical calls, function namespaces,
and the executive lock wrapper. Shared caching is appropriate because authorized
workspaces share the analytics dataset; authorization is checked separately.
See [cache coverage](cache-coverage.md).

VULN-07 is **implemented and verified offline**. A dedicated, private token
issuer creates a signed HttpOnly security nonce cookie. Header tokens are HMACs
bound to that nonce and the current access cookie. Exact Origin checks and CSRF
validation precede browser-triggered mutations, including pre-login session
POST/DELETE, workspace switching, and Dash governance callbacks. The frontend
acquires fresh tokens only for allowlisted same-origin app requests, never
forwards them to Supabase, preserves concurrent callbacks, and never replays
rejected writes. Flask session remains workspace-only. See
[CSRF lifecycle and operational limits](csrf-protection.md).

VULN-08's repository work is **implemented and verified offline**. Bootstrap
requires an explicit TCP host, pins it against libpq service overrides, enforces
certificate/hostname verification before password authentication, checks actual
negotiated TLS before SQL, and sanitizes driver/DSN errors. The runbook uses
filename-only discovery and protected runtime secret injection; it distinguishes
hosted Supabase privileges from true superuser/RLS capabilities. See
[bootstrap credentials and rotation](bootstrap-credentials.md).

**Production credential rotation remains pending** separate authorization and
operator evidence. No production connections, real accounts, bootstrap, ELT,
dbt, password rotation, or role grants were performed. Code-level tests do not
establish live deployment behavior or completion of operational rotation.

The combined Python 3.12 candidate passes all 196 offline Python tests.
Frontend build, tests, full repository hooks and dependency audit are recorded in
[the Phase 3 implementation/review record](security-phase3.md).

## Conclusion

The Postgres-AdventureWorksDW project has a strong security foundation with proper database-level access controls, comprehensive audit logging, and thoughtful authentication architecture. **Phase 1 critical vulnerabilities have been addressed** with identifier validation for SQL construction and a corrected `.gitignore` pattern. Phase 2 code remediation and Phase 3 offline evidence are recorded above. Operational Redis configuration, deployment verification, and production credential rotation require their own evidence; repository checks do not establish production readiness.

**Note:** This report reflects code-level verification only. No live production BigQuery queries were executed, no ELT/dbt destructive operations were run, and no real accounts were created during validation. Phase 1 completion is based on static analysis, unit test results (108 tests passing), and git ignore behavior checks.
