# Security Audit Report: Postgres-AdventureWorksDW

## Executive Summary

A security audit was conducted of the Postgres-AdventureWorksDW data analytics dashboard project. The assessment covered authentication/authorization architecture, database governance, credential management, API surface exposure, container hardening, and data pipeline safety.

**Overall Rating: LOW-MEDIUM RISK**

The project demonstrates strong foundational security practices including Supabase row-level security (RLS), security-definer RPC boundaries, email-first registration enforcement, password lockout mechanisms, and comprehensive audit logging. However, several areas require attention: SQL injection exposure in KPI query builders, overly permissive `.gitignore` patterns, missing rate-limiting on public endpoints, and insufficient dependency pinning.

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

**Description:** The cache directory is created with `0o700` permissions, which is appropriate. However, the cache key generation does not include all relevant query parameters, potentially returning stale data when filter parameters change. This is a data integrity concern rather than a security vulnerability.

**Impact:** Users may see stale KPI data when filters change, leading to incorrect business decisions.

**Remediation:** Ensure cache keys include all filter parameters (date range, segment, workspace ID). Consider shorter TTLs for time-sensitive KPIs.

---

### VULN-07: Missing CSRF Protection on State-Changing RPCs

**Severity:** LOW
**Location:** `my-dash-app/governance.py`, `my-dash-app/pages/workspace_admin.py`
**CWE:** CWE-352

**Description:** While the application uses Supabase Auth with access tokens in cookies, the governance RPC calls (workspace creation, member changes, approval decisions) rely on Bearer token validation without CSRF token validation. If cookies are `SameSite=Lax` (as documented), the risk is mitigated, but explicit CSRF tokens would provide defense-in-depth.

**Impact:** In the event of cookie misconfiguration, an attacker could forge state-changing requests on behalf of authenticated users.

**Remediation:** Verify `SameSite=Lax` or `Strict` is enforced at the Flask cookie jar configuration. Add optional CSRF token validation for high-impact operations.

---

### VULN-08: Bootstrap Script Uses Direct Database Connection

**Severity:** LOW
**Location:** `scripts/bootstrap_workspace.py`
**CWE:** CWE-798

**Description:** The bootstrap script accepts `SUPABASE_DB_URL` from environment variables and uses it to connect directly to PostgreSQL. While the script is documented as "never imported or exposed by the web application," it still represents a credential handling point. The URL is loaded from `.env` with `override=False`, which is appropriate.

**Impact:** If the `.env` file is compromised, the database connection URL is exposed. The script also bypasses all RLS policies by connecting directly.

**Remediation:** This is acceptable for a CLI-only bootstrap tool. Ensure the `SUPABASE_DB_URL` uses a least-privilege database role. Never run this script in web context. The existing advisory lock and idempotency checks are good controls.

---

## Strengths Observed

1. **RLS + Security Definer Pattern:** The governance schema uses PostgreSQL RLS with security-definer functions as the only write path, preventing direct client-side data manipulation.

2. **Email-First Registration:** Migration 0002 enforces that all users must register with email before OAuth sign-in is permitted.

3. **Verified Email Enforcement:** Migration 0003 adds `email_confirmed_at` checks to all approval and membership RPCs.

4. **Password Lockout:** Migration 0005 implements 5-attempt lockout with 15-minute cooldown, with proper invalid-credential signaling.

5. **Audit Trail:** All governance actions are logged to `governance_audit_events` with actor, action, and details.

6. **Token Hygiene:** Recovery tokens stay in URL fragments (not logged by HTTP servers). Access/refresh tokens never enter Flask or Dash.

7. **Cookie Security:** Cookies are HttpOnly and SameSite=Lax as documented.

8. **Container Hardening:** Dockerfile creates non-root user `dashapp` and switches to it.

9. **Least Privilege:** Platform admin bootstrap is CLI-only with advisory lock.

---

## Prioritized Remediation Plan

### Phase 1: Critical (0-2 weeks)
| ID | Action | Effort |
|----|--------|--------|
| VULN-01 | Parameterize all SQL queries in `customer_kpis.py` and `revenue_kpis.py` | 3 days |
| VULN-02 | Replace `*.json` gitignore with explicit file rules | 1 hour |

### Phase 2: High (2-4 weeks)
| ID | Action | Effort |
|----|--------|--------|
| VULN-03 | Implement Flask-Limiter on all auth endpoints | 2 days |
| VULN-04 | Pin exact dependency versions; add `pip-audit` to CI | 2 days |
| VULN-05 | Add environment guards and confirmation flags to `elt_pipeline.py` | 3 days |

### Phase 3: Medium (4-8 weeks)
| ID | Action | Effort |
|----|--------|--------|
| VULN-06 | Fix cache key parameter coverage in KPI modules | 1 day |
| VULN-07 | Add CSRF token validation for state-changing RPCs | 2 days |
| VULN-08 | Document `SUPABASE_DB_URL` handling; rotate credentials | 1 hour |

### Phase 4: Ongoing
- Implement automated security scanning (SAST + dependency audit) in CI/CD
- Conduct periodic penetration testing of the auth flow
- Review and rotate Supabase anon/publishable keys annually
- Monitor `governance_audit_events` for anomalous patterns

---

## Conclusion

The Postgres-AdventureWorksDW project has a strong security foundation with proper database-level access controls, comprehensive audit logging, and thoughtful authentication architecture. The identified vulnerabilities are primarily related to input handling in query builders, operational safeguards for destructive pipelines, and defense-in-depth improvements. Addressing the critical and high-priority items will bring the project to a production-ready security posture.