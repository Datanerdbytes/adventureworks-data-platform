# KPI cache parameter coverage

Phase 3 VULN-06 was investigated against the existing memoized loaders and their
page callbacks. No omitted query parameter was reproduced. Flask-Caching's
`memoize` includes the function identity and its bound arguments, including
defaults; the application does not replace that key generation. The regression
suite verifies this behavior through the actual decorators and an isolated
FileSystemCache, with BigQuery clients mocked before any loader executes.

## Covered loaders and inputs

| Module           | Memoized loaders                                                                              | Query-affecting arguments                                                                |
| ---------------- | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `revenue_kpis`   | Revenue totals, filter catalog                                                                | Project, analytics dataset                                                               |
| `revenue_kpis`   | Executive report                                                                              | Project, analytics dataset, year, quarter, channel, category, subcategory                |
| `customer_kpis`  | Scorecards, demographics, map, lifecycle, segment revenue, ledger                             | Project, analytics dataset, five sales filters; segment revenue also includes dimension  |
| `growth_kpis`    | Scorecards, day-type sales, seasonality matrix, ledger                                        | Project, analytics dataset, five sales filters                                           |
| `wholesale_kpis` | Active accounts, revenue, orders, comparison, top resellers, scatter, product mix, operations | Project, analytics dataset, five sales filters; operations also includes staging dataset |

The tests inventory all 21 decorated loaders so a new loader cannot silently
escape coverage. Each argument is varied independently: a warehouse query must
occur and its response must differ from the cached baseline. Repeating either
selection must reuse its response. Query text or typed BigQuery parameters also
confirm the changed input reaches the query. Positional, keyword, and omitted
optional defaults reuse the same entry. Separate functions cannot share entries
solely because their arguments match.

The executive public wrapper computes its bounded lock stripe from the same
complete argument tuple passed to its memoized inner loader. Additional tests
exercise this wrapper with real temporary lock files. Stripe collisions can
serialize unrelated requests but do not merge their cached results.

## Configuration, workspace scope, and freshness

Page callbacks resolve `GBQ_PROJECT_ID` and `BQ_ANALYTICS_DATASET` before calling
the loaders, which receive both as explicit arguments. Wholesale operations also
resolves `BQ_STAGING_DATASET` before calling its loader. Changing these settings
therefore selects distinct cache entries. No KPI loader resolves a warehouse
identifier from hidden environment state after key generation.

All authorized workspaces currently read the same AdventureWorks dataset and
these loaders return no workspace-specific or user-specific results. Sharing
analytics cache entries is appropriate under that model. Authorization and
current workspace membership are validated independently on protected requests;
the KPI cache must never substitute for that validation. If row-level workspace
scope or user-specific query results are introduced, the scope must become an
explicit loader argument and gain an isolation regression test.

There are no query pagination arguments in these modules: SQL limits are fixed,
and pages paginate the returned rows in their grids. If server-side offset,
cursor, page size, or sort arguments are introduced, they must enter the loader
signature and the coverage matrix.

Warehouse data changes and mart deployment availability are ordinary freshness
concerns, not omitted user filters. Growth scorecards and customer maps choose
mart/fact fallback inside the load; cached results may retain that choice until
expiry. Existing TTLs remain 60 seconds for KPI results and 300 seconds for the
filter catalog. No shorter TTL or speculative key rewrite was introduced.

## Offline verification

```sh
uv run --locked python -B -m unittest discover -s tests -p test_cache_coverage.py -v
```

The tests run real cache lookup/storage and loader SQL/configuration assembly;
all warehouse responses are synthetic. They perform no production queries.
VULN-06's alleged parameter omission is not substantiated in this baseline;
the evidence supports closing it as verified existing coverage, with these tests
preventing regressions rather than claiming a production fix was made.
