# KPI cache parameter coverage

Phase 3 VULN-06 was investigated against the existing loaders and page callbacks;
no omitted query parameter was reproduced. The performance implementation now
uses `warehouse_cache.warehouse_memoize` over the shared Flask-Caching
FileSystemCache. Its canonical identity binds the original function signature,
applies omitted defaults, and serializes the module, function name and every
argument before SHA-256 hashing. The same key governs lookup and coordination.
This avoids separate memoization version metadata racing during a cold start.
The `warehouse-v1:` namespace isolates the new tuple-envelope storage format from
old Flask-Caching entries; old entries expire normally. No credentials or tokens
are accepted as loader inputs or written to lock names.

## Covered loaders and inputs

| Module           | Memoized loaders                                                                              | Query-affecting arguments                                                                |
| ---------------- | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `revenue_kpis`   | Revenue totals, filter catalog                                                                | Project, analytics dataset                                                               |
| `revenue_kpis`   | Executive report                                                                              | Project, analytics dataset, year, quarter, channel, category, subcategory                |
| `customer_kpis`  | Scorecards, demographics, map, lifecycle, segment revenue, ledger                             | Project, analytics dataset, five sales filters; segment revenue also includes dimension  |
| `growth_kpis`    | Scorecards, day-type sales, seasonality matrix, ledger                                        | Project, analytics dataset, five sales filters                                           |
| `wholesale_kpis` | Active accounts, revenue, orders, comparison, top resellers, scatter, product mix, operations | Project, analytics dataset, five sales filters; operations also includes staging dataset |

All 21 report loaders remain inventoried by their `make_cache_key` attribute, including
`_load_executive_report` behind its unchanged public forwarding function. The
wrapper retains the original signature, `__wrapped__`, and `uncached` attributes.
Its `make_cache_key(*args, **kwargs)` returns the canonical key directly; this is
an application wrapper, not Flask-Caching's decorator API. No application caller
uses Flask-Caching's per-function `delete_memoized`; whole backend clearing is
reserved for isolated tests. Changing result semantics requires a namespace
version change or an operator-managed cache invalidation.

Each argument is varied independently: a warehouse query must occur and its
response must differ from the cached baseline. Repeating either selection reuses
its response. Query text or typed BigQuery parameters confirms that each changed
input reaches the query. Positional, keyword and omitted optional defaults reuse
the same entry. Separate functions cannot share entries solely because their
arguments match.

## Capacity and freshness

`init_kpi_cache` reads `KPI_CACHE_THRESHOLD` at server startup, default **500**.
It accepts a positive integer, rejects malformed/zero/negative values before
backend initialization, and allows Flask server configuration to override the
environment. This is a finite entry budget, not a byte bound or a measured
optimal production setting. CacheLib prunes when its threshold is exceeded; the
threshold is not an exact hard maximum file count. No browser setting controls
it. Real isolated-cache tests show the former threshold of 10 evicting still-live
results, and the default retaining three dataset selections across all 21
loaders, including the derived comparison's additional direct-loader entries.
Assertions use returned markers and warehouse call counts, not private counters.

TTLs remain **60 seconds** for results and **300 seconds** for the filter catalog.
Successful `None` results are now retained for the result TTL using one-element
tuple envelopes. Previously Flask-Caching's default treated a cached `None` as a
miss. A single atomic lookup now distinguishes a missing entry from a successful
empty response without a racy separate existence check. Warehouse exceptions
propagate and are never converted to cached empty successes.

## Coordinating warehouse misses

All **20 direct warehouse loaders** use nonblocking `flock` with bounded waiting.
Cache hits bypass the lock. After acquiring it, workers recheck the actual entry
before executing warehouse work, including schema checks and mart/fact fallback.
The successful result is published before releasing the lock. Exceptions release
it, and the operating system releases it when a process terminates.

`KPI_CACHE_LOCK_TIMEOUT_SECONDS` defaults to **30 seconds** and must be finite and
positive. It is read and validated during startup, with Flask server config taking
precedence over the environment. A waiting request raises `TimeoutError` after
that deadline; it does not query without coordination or publish fake success.
The wait deadline does not change BigQuery's existing query/result timeouts.

There are at most **64 private lock files**, created with mode `0600` in the
application's private temporary lock directory. Different keys may share a stripe
and serialize, but they never share results. Noncolliding stripes proceed
independently. `load_wholesale_comparison` is a derived memoized loader and
**does not acquire a lock**; it calls three individually coordinated warehouse
loaders sequentially. This eliminates nested lock acquisition even if every key
collides. The executive public wrapper also adds no second lock.

Coordination requires workers to share the same cache and lock filesystem, as in
the current single-container Gunicorn setup. It does not coordinate separate
containers/hosts or provide Redis/distributed single-flight. The guarantee also
requires successful cache publication and a retained, unexpired entry: backend
failure, eviction or TTL expiry can cause a later worker to query again.

## Workspace scope

Page callbacks resolve `GBQ_PROJECT_ID` and `BQ_ANALYTICS_DATASET` before calling
the loaders; wholesale operations also resolves `BQ_STAGING_DATASET`. Each is an
explicit argument, so configuration changes select distinct entries. No warehouse
identifier is resolved from hidden environment state after key generation.

All authorized workspaces currently read the same AdventureWorks dataset. These
loaders return no workspace-specific/user-specific results. Authorization and
current membership are validated independently on protected requests; the cache
never substitutes for that validation. Future row-level scope, pagination or
sorting must enter loader arguments, canonical keys and isolation tests.

Warehouse changes and mart availability remain ordinary freshness concerns;
cached fallback decisions may persist until expiry. No query SQL, billing limits,
filter behavior, authentication or financial precision changes are included.

## Offline verification

```sh
uv run --locked python -B -m unittest discover -s tests -p 'test_cache*.py' -v
uv run --locked python scripts/pre_commit_checks.py python-tests
```

Tests use temporary real FileSystemCache/lock directories and mocked warehouse
responses. Every direct loader is requested by two synchronized processes for a
cold key and again after deterministic clock advancement past its TTL. Additional
tests cover positional/keyword equivalence, successful None caching, failed
workers, timeout, process termination, independent stripes, forced collisions
through the derived comparison, and bounded private lock files. Worker barriers,
events and joins have deadlines. Tests perform no production queries and do not
clear the application's shared backend. Local tests do not establish live schema,
production latency/cost/hit rates, multi-container sharing or a memory budget.

## Warehouse table previews

`warehouse_tables.load_table_preview(project, dataset, name)` is the additional
60-second cached loader for `/tables`. `name` is an allowlisted Products, Customers
or Sales selection. Tests in `tests/test_warehouse_tables.py` use the real isolated
cache to verify project, dataset and selection isolation and reuse. Search and
page size affect only the loaded grid, so they do not belong in its warehouse
cache identity. Rows are capped at 500 (with one sentinel row queried), queries
use explicit columns/stable key ordering and a 100 MiB billing ceiling. Workspaces
continue to share the same analytics dataset.
