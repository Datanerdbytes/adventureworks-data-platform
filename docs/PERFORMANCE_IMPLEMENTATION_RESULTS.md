# Performance implementation: acceptance record

Completed locally on 2026-10-15 on `codex/performance-integration`. The combined
code candidate is `58b202fd7a365fd066a3e49c118d722838b845ca`, based on
`7020dd0e0c774697ba2e5f3c78e9417c28d64537`. Later documentation-only commits
record this evidence. Nothing was pushed, merged into `integration`, deployed,
or executed against live services.

## Contributions and integration

Three agents worked in separate managed worktrees with disjoint ownership. The
coordinator inspected their diffs and acceptance evidence and integrated serially.
The measurement agent also independently reviewed the cache and ELT code.

| Track                             | Submission                                                                                           | Integrated commit | Disposition                                                                                        |
| --------------------------------- | ---------------------------------------------------------------------------------------------------- | ----------------- | -------------------------------------------------------------------------------------------------- |
| M: offline characterization       | `60b52489ef5e055bc9ecb3677971aeb26c9b68be`                                                           | `b671e41`         | Accepted; synthetic baselines and reproducible script                                              |
| C: capacity and concurrent misses | `1fad3c99f2672f87a7d814ef568af97d57902ce7`                                                           | `06bcb3e`         | Accepted; existing loader interfaces and query semantics retained                                  |
| E: bounded extraction             | Reviewed five-file patch, SHA-256 `862e8918038a1923754d0a78828f2eb9c3e1cccd8b0a2484a6c27223e3ee57d2` | `58b202f`         | Accepted after temporal-schema correction; coordinator committed patch and shared baseline refresh |

E's worker commit was prevented by automatic approval review of a shared
`.secrets.baseline` edit outside its assigned file ownership. The worker supplied
its owned-file patch instead. The integration owner changed only the existing
synthetic credential finding's line number, 364 to 377. Finding hash, reviewed
status, scanner configuration, and every other baseline field remain unchanged.
Normal hooks then passed; no check was bypassed.

The original `docs/PERFORMANCE_AUDIT.md` contents were preserved. Its pre-existing
staged state is restored after the integration commits. Initial audit/plan state
was saved in `/private/tmp/aw-performance-review-preserved/staged-docs.patch`.

## Acceptance matrix

| Requirement                                 | Implementation and verification                                                                                                                                                                                                                                                | Result         |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------- |
| Bounded cache capacity, unchanged freshness | `init_kpi_cache`: validated `KPI_CACHE_THRESHOLD=500`; malformed/zero/negative rejected; actual real-cache working set shows threshold 10 evicts live results and 500 retains selections across all 21 loaders; result/catalog TTLs remain 60/300 seconds                      | Passed         |
| Same-key concurrent misses                  | `warehouse_cache.py`: canonical bound/defaulted arguments and function identity for both entries and lock stripes; recheck under lock; every one of 20 direct warehouse loaders tested with synchronized processes on cold and deterministically expired keys                  | Passed         |
| Isolation, bounded wait, recovery           | Per-input coverage retained; defaults/positional/keyword equivalence; cached None envelope; warehouse exceptions not cached; timeout and terminated holder recovery; independent stripes; forced collision through derived wholesale comparison; at most 64 private lock files | Passed         |
| Bounded ELT consumption                     | Streaming source cursor options and fixed `fetchmany`; weak-reference tests reject retained prior batches; default 10,000 rows, validated maximum 100,000; no full-table row list or DataFrame                                                                                 | Passed offline |
| Complete per-table publication              | Incremental typed Parquet spool; writer/footer closed before one final `WRITE_TRUNCATE` file load; actual file read-back at fake upload verifies all rows/types; empty tables skip; extraction/conversion/disk/footer failures submit no replacement                           | Passed offline |
| Explicit temporal load types                | Review found missing schema could change naive datetime columns to TIMESTAMP; corrected load config reads closed-file schema and explicitly chooses DATETIME for naive and TIMESTAMP for aware values; end-to-end mocked upload regression covers null-first temporal types    | Passed         |
| Safety and lifecycle                        | Existing preflight, destination, production confirmation, and sanitized-error tests retained; dry-run creates no clients/spool; result/connection/writer/temp/client/engine cleanup and client initialization failure covered                                                  | Passed offline |
| Evidence-led deferred work                  | New opt-in script measures actual map figures and serialization, documented indexing/aggregation proxies, and pure staging helper; no SQL rewrites, UI changes, Redis migration, or background infrastructure added                                                            | Passed         |
| Combined regression/code quality            | Full safe Python and frontend suites, applicable normal commit hooks, whole-repository configured Bandit and document formatting                                                                                                                                               | Passed         |

## Deliberate compatibility choices

Schema is based on source metadata rather than whichever values arrive first.
Nullable integer and boolean columns retain their source types even if the first
batch is null; this can replace previous incidental pandas float/object inference.
The coordinator accepted this adjustment to meet stable-schema/null-first
requirements. Numeric/Decimal still converts to float64 as before; this is not a
new lossless financial export. Naive/aware timestamp semantics are explicitly
preserved through the BigQuery load schema. Unsupported source types fail the
table before publication; a live production type inventory was not obtained.

Memoization now uses application-owned canonical keys over Flask-Caching storage,
avoiding separate version-key races during simultaneous cold loads. All 21
loaders and their inputs remain inventoried. No application caller relied on
Flask-Caching's per-function deletion API. Cache hits avoid locking; the derived
comparison does not hold a lock while calling direct loaders. Successful empty
None results are now retained for the ordinary TTL.

## Executed checks

On combined code candidate `58b202fd7a365fd066a3e49c118d722838b845ca`:

```sh
UV_CACHE_DIR=/private/tmp/adventureworks-performance-uv-cache uv run --locked python scripts/pre_commit_checks.py python-tests
npm run test:auth
UV_CACHE_DIR=/private/tmp/adventureworks-performance-uv-cache uv run --locked pre-commit run bandit --all-files --show-diff-on-failure
UV_CACHE_DIR=/private/tmp/adventureworks-performance-uv-cache uv run --locked python scripts/benchmark_performance.py --repetitions 5 --elt-memory
```

- **232 Python tests passed**, 9.606 seconds; all service responses mocked.
- **28 auth frontend tests passed**, zero failures/skips.
- Configured whole-repository Bandit passed. Normal implementation commit hooks
  passed Ruff, Black, mypy, Bandit, secrets, syntax/hygiene, Python and auth tests.
- Installed Prettier checks passed for the review, plan, cache, ELT, and benchmark
  documents. `git diff --check` passed on the combined code candidate.
- Combined benchmark correctness invariants passed, including aliases, Decimal
  currency, and empty/unlocated selections. A 2,001-row map fixture is rejected
  by the opt-in command; measurements stay within the 2,000-group loader contract.

Local evidence logs:

- `/private/tmp/aw-performance-combined-tests.log`
- `/private/tmp/aw-performance-auth-tests.log`
- `/private/tmp/aw-performance-bandit.log`
- `/private/tmp/aw-performance-combined-benchmark.json`

These temporary files are reproducible evidence, not portable source dependencies.
The versioned methodology and earlier full baseline are in
[performance-benchmark.md](performance-benchmark.md).

## Combined synthetic measurement

Five timed repetitions plus separate allocation samples, batch size 1,000:

| Rows      | Median staging ms | Python traced peak bytes | Arrow allocator peak bytes | Temporary spool bytes |
| --------- | ----------------- | ------------------------ | -------------------------- | --------------------- |
| 10,000    | 12.1492           | 651,665                  | 36,224                     | 122,164               |
| 100,000   | 138.8190          | 651,537                  | 36,224                     | 1,217,928             |
| 1,000,000 | 1338.4801         | 651,409                  | 36,224                     | 12,182,501            |

The pure helper fingerprint matches the worker baseline:
`50b413d8f9930b95e809564ae482a50c9b50b344b4c4bb21dd7eba3bc07bcf03`.
These allocation observations exclude real driver buffering, full RSS, BigQuery
upload, and other native allocations. Parquet metadata grows with row groups;
row count bounds do not bound cell sizes. Disk grows with table size.

At 2,000 synthetic map rows, median whole-figure time was 11.9543 ms for overview
and 26.2581 ms for Europe drilldown; JSON payloads were 62,795 and 315,978 bytes.
This distribution intentionally includes many unknown geographies and establishes
no production latency or severity. No map optimization was justified by this run.

## Remaining operational limits

- Filesystem coordination covers workers sharing local cache/lock directories;
  separate containers/hosts require a separate distributed design. Cache write
  failure, eviction, and expiry can cause subsequent queries.
- Cache capacity is an entry budget, not a byte limit. Current result freshness
  and authorization remain unchanged.
- ELT still reads and replaces full tables. Each table publishes after complete
  staging; earlier successful tables are not rolled back if a later table fails.
  Temporary disk capacity and interrupted-process cleanup require normal operator
  management.
- No live schema/type inventory, warehouse query plan, production load test,
  latency/cost measurement, Redis check, deployment, or production ingestion was
  performed. These are outside this implementation's acceptance scope.

Technical references used to resolve the schema review finding:
[BigQuery Parquet conversion types](https://docs.cloud.google.com/bigquery/docs/loading-data-cloud-storage-parquet#type_conversions),
[BigQuery DATETIME Parquet handling](https://docs.cloud.google.com/bigquery/docs/exporting-data#parquet_export_details),
and [SQLAlchemy streaming execution](https://docs.sqlalchemy.org/en/21/core/connections.html#using-server-side-cursors-a-k-a-stream-results).
