# Security check boundaries

The repository scan found potential risks that require context rather than broad
scanner exclusions. The cleanup keeps Bandit and detect-secrets enabled.

## SQL templates

The revenue, customer, growth, and wholesale KPI modules share
`validate_warehouse_identifiers()`. Every builder and loader validates project and
analytics dataset arguments; wholesale operations also validates its staging
dataset. Invalid identifier types or SQL metacharacters fail before BigQuery client
creation, including direct loader calls and the customer-map fallback path.

All report filter values continue to use typed BigQuery query parameters. The
customer segment expression is selected from `DEMOGRAPHIC_DIMENSIONS`; an unknown
key cannot inject SQL. The ELT source query uses the fixed AdventureWorks table
list. The user-facing query semantics, aggregation grains, timeouts, and scan
limits are preserved.

`# nosec B608` annotations apply only to these reviewed SQL expressions. They
acknowledge necessary table-identifier interpolation; they do not permit raw
filter values in SQL. Future template edits must preserve the identifier guards
and value binding. Regression tests reject malformed identifiers for all builders
and loaders, reject a malicious demographic dimension, check staging identifiers,
and confirm that a hostile category stays in query parameters instead of SQL.

## Supabase transport

`SupabaseGateway` validates the base URL before constructing requests. HTTPS is
required except for explicit HTTP loopback URLs used in local development. Embedded
credentials, malformed ports, fragments, query strings in base URLs, backslashes,
control characters, and unexpected base paths are rejected. API request paths
cannot supply a different authority or fragment.

The transport validates the final URL and disables redirects. A redirect cannot
forward API keys or bearer tokens to another service. Existing response size,
timeout, error sanitization, confirmation, and workspace authorization checks
remain in place. Tests cover rejected schemes/paths and redirect handling using
mocked transports. This does not replace live deployment/proxy verification.

## Subprocess checks and fixture secrets

The hook runner's B404/B603 annotations cover its fixed lint/test/advisory command
lists, with no shell execution. JavaScript inputs are parsed with `node --check`,
not executed. The runner never invokes ELT, dbt, or database governance scripts.

The synthetic credential URL and bearer/header fixture in
`test_security_boundaries.py` have inline `pragma: allowlist secret` annotations. The existing secret baseline still approves
only its seven previously reviewed fixture/library/digest fingerprints. Real
credentials are never included in these exceptions, and scanning disables network
credential verification.
