# Performance implementation handoff

Prepared 2026-10-15. Status: **implemented, reviewed, verified offline, and integrated locally**.

Accepted code candidate: `58b202fd7a365fd066a3e49c118d722838b845ca` on
`codex/performance-integration`. See the [acceptance record](PERFORMANCE_IMPLEMENTATION_RESULTS.md)
for submitted commits, review corrections, commands/results, and operational
limits. No push, merge into `integration`, deployment, or live execution occurred.

Read [the audit review](PERFORMANCE_AUDIT_REVIEW.md) before implementing. The
original audit is a set of allegations, not an acceptance specification.

## Baseline and scope

- Observed branch: `integration`.
- Observed base: `7020dd0e0c774697ba2e5f3c78e9417c28d64537`.
- Existing staged/unstaged changes: `docs/PERFORMANCE_AUDIT.md`; preserve them.
- The user subsequently authorized this chat to implement the plan with parallel
  agents. The coordinator owns shared configuration, serial integration, and
  acceptance review; workers own C, E, and M in isolated managed worktrees.
- Integration candidate: `codex/performance-integration` in the original checkout.
- Worker checkouts: managed `performance-cache`, `performance-elt`, and
  `performance-measurements` worktrees, each created at the observed base above.
- Existing staged documents were preserved in
  `/private/tmp/aw-performance-review-preserved/staged-docs.patch` before edits.
- Recheck HEAD, worktrees, applicable `AGENTS.md`, and active writers before
  starting. Record the actual implementation base if it changed.
- Use isolated worktrees and disjoint file ownership for parallel workers.
  Reuse suitable attached worktrees. Do not overwrite another agent's changes.
- No live warehouse reads, Supabase operations, account creation, Redis access,
  migrations, ingestion, deployment, push, or merge is required by this plan.
  Production ELT retains the repository's separate multi-turn authorization rule.
- Preserve dependency pins, current loader signatures and return shapes,
  parameterized SQL, billing limits, timeouts, filter semantics, financial
  precision, authentication, CSRF, and fail-closed authorization.

## Parallel tracks and ownership

| Track                                     | Priority and evidence                         | Exclusive files                                                                                                                                                                                                                     | Dependencies                                                                 | Status / submitted SHA                |
| ----------------------------------------- | --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------- |
| C — Cache capacity and miss coalescing    | First web-path improvement; F02, A01          | `my-dash-app/revenue_kpis.py`, `growth_kpis.py`, `customer_kpis.py`, `wholesale_kpis.py`; a new cache coordination helper if needed; `tests/test_cache_coverage.py`; new cache concurrency/capacity tests; `docs/cache-coverage.md` | No dependency on E; implement C1 before C2                                   | Accepted / `1fad3c9`                  |
| E — Bounded ELT extraction and lifecycle  | Confirmed unbounded memory; F09, A02          | `elt_pipeline.py`; new extraction/staging helper if needed; `tests/test_elt_pipeline.py`; new ELT streaming tests; `docs/elt-safety.md`                                                                                             | No dependency on C                                                           | Accepted patch / integrated `58b202f` |
| M — Reproducible offline characterization | Establish evidence for deferred optimizations | New `scripts/benchmark_performance.py`, new `docs/performance-benchmark.md` only                                                                                                                                                    | May run concurrently; use existing public interfaces and temporary resources | Accepted / `60b5248`                  |
| I — Integration and independent review    | All acceptance requirements                   | This plan, review evidence, and shared configuration only after ordered handoff                                                                                                                                                     | C, E, M submissions                                                          | Verified / `58b202f`                  |

One implementing agent may coordinate these tracks with parallel workers. Shared
files such as `.env.example`, `pyproject.toml`, `uv.lock`, or hook configuration
belong to I; propose changes to that owner instead of editing them independently.
No dependency changes are expected. M must not rewrite C/E code while measuring.
The independent reviewer must inspect submitted diffs, not rely on worker claims.

## C1 — Capacity before expiry tuning

1. Reproduce early eviction with the actual production threshold and an isolated
   real FileSystemCache. Include enough distinct live loader/filter entries and
   memoization metadata to exceed capacity. Do not clear the application's cache.
2. Make capacity a validated, finite positive server configuration. Proposed
   contract: `KPI_CACHE_THRESHOLD`, default **500**, read during cache setup;
   reject malformed, zero, and negative values. Document that this is an entry
   budget, not a byte bound or a measured optimal production value. Do not add a
   browser setting. Coordinate `.env.example` edits with I.
3. Preserve 60-second result TTL and 300-second catalog TTL. Validate normal
   reuse across a representative working set of all loaders plus several filter
   combinations, without relying on private CacheLib counters as the assertion.
   Observe fake warehouse call counts and distinct returned markers.

Acceptance: the former small threshold demonstrably evicts still-live test data;
the selected bounded default retains the representative working set; repeated
queries reuse results; invalid capacity fails clearly without exposing secrets.
Do not claim this fixes multi-instance sharing or guarantees a memory budget.

## C2 — Coalesce cold/expired warehouse loads

1. Reuse or extract the executive report's existing shared-file locking approach
   for the current Linux/Gunicorn single-filesystem deployment. Keep lock-file
   count bounded and private; state explicitly that it does not coordinate
   separate containers/hosts.
2. Define one canonical identity from loader identity plus bound/defaulted query
   arguments. Preserve positional/keyword equivalence, every filter, dimension,
   and analytics/staging dataset. The same identity must govern memoization and
   coalescing. Do not use bearer tokens or credentials in names/keys.
3. Recheck the real memoized entry after acquiring coordination. Locking only the
   underlying query after an outer cache miss is insufficient: waiters would
   still repeat queries without this second check. Retain successful return
   shapes and exception propagation. Do not cache failures as successful empty
   results. Account explicitly for existing `None` return caching behavior.
4. Inventory direct warehouse loaders versus derived loaders, especially
   `load_wholesale_comparison`, which calls other loaders. Coordinate at the
   warehouse boundary and avoid nested acquisition of the same non-reentrant
   lock stripe. Include function identity and a safe lock hierarchy or eliminate
   nested locks; merely adding function names to a hash does not rule out stripe
   collisions. Preserve existing executive protection without double locking.
5. Bound lock waiting with a documented timeout and controlled failure; ensure
   all exceptions release coordination. A crashed process must not leave a
   permanent application-level lease. Do not serialize all filters globally.
6. Update loader inventory introspection only as required by wrapper changes;
   retain complete behavioral coverage. Do not remove coverage to make wrappers
   pass the inventory test.

Acceptance tests must use temporary shared cache/lock directories and fake
warehouse calls, never a real warehouse client:

- Two synchronized processes request the same cold key: one query, two correct
  results. Repeat for an expired key using deterministic time control where
  practical. Sequential reuse alone is insufficient evidence.
- Different functions, filters, dimensions, and datasets remain isolated.
  Demonstrate independent progress for distinct noncolliding lock identities.
- Positional, keyword, and omitted-default calls coalesce consistently.
- Failure and lock timeout do not cache fake success; subsequent calls can
  recover. Worker exceptions and process termination do not deadlock followers.
- Force stripe collision/nested derived-loader scenarios to verify no deadlock.
- All 21 existing loaders remain inventoried, or document the new equivalent
  public/private mapping if refactoring changes the decorator count.

Use bounded barriers/events and join deadlines in concurrency tests. Avoid
fragile millisecond speed assertions. Cache hits/misses and call counts are
correctness evidence; live p95/cost improvement remains unverified.

## E — Bounded reads with complete replacement publication

The current pipeline builds full-table rows, dictionaries, and a DataFrame. A
simple `chunksize` parameter does not prove bounded memory if the database driver
buffers the result or if chunks are accumulated before upload.

1. Keep preflight, destination validation, and production confirmation before any
   engine/client construction, source read, staging, or upload. Dry-run stays
   network-free and does not create clients or temporary export files.
2. Use a server-side streaming SQLAlchemy/PostgreSQL cursor with a validated,
   bounded batch size and `fetchmany`/equivalent iteration. Never call `fetchall`,
   build a whole-table record list, concatenate all batches, or retain past
   DataFrames. Keep the source result/connection lifetime valid while iterating.
3. Prefer a local temporary Parquet spool using the existing PyArrow dependency:
   write one batch at a time, close the writer, then submit **one** BigQuery file
   load with `WRITE_TRUNCATE` for that table. Local disk grows with table size;
   memory should grow with batch size. Check available temporary capacity or
   handle exhaustion safely, and document the disk tradeoff.
4. Establish a stable schema across batches. Do not infer permanently from an
   all-null first batch. Handle dates, timestamps, nullable integers/booleans,
   strings, and financial numeric values consistently. Preserve current
   externally observed conversion semantics unless a separate correctness change
   is documented and approved for scope. In particular, map Decimal handling to
   the current pipeline behavior deliberately; do not change types accidentally.
5. Retain the existing behavior for empty source tables: report skipped and leave
   the destination unchanged. Changing empty-table semantics is separate work.
6. Publish only after successful extraction and serialization of all batches.
   Never truncate/append production destinations per chunk. A serialization or
   source failure must submit no destination replacement. A failed final load
   must not be reported as successful. Retain per-table failure reporting and
   nonzero final status, and avoid credential-bearing exception strings.
7. Close results, connections, temporary files/writers, BigQuery client, and
   dispose the engine on all exits. Handle client-construction failure after
   engine creation as well as failures inside individual tables. Do not mask the
   original failure with cleanup exceptions.

Acceptance tests with synthetic rows and mocked clients:

- A fake source rejects `fetchall` and oversized fetch requests. Processing many
  batches uses incremental consumption and bounded outstanding batch storage.
  Verify the configured server-side cursor behavior is requested; a mocked
  iterator alone does not prove driver streaming.
- Read the produced temporary Parquet file inside the fake upload boundary and
  assert every row appears once with correct types across batch boundaries,
  including all-null first batch, later non-null data, Decimal, dates, and nulls.
- Exactly one final load per nonempty table, correct destination/region and
  `WRITE_TRUNCATE`; empty table submits none.
- Mid-extraction, serialization, disk, and upload failures preserve reporting and
  cleanup. Source/serialization failures submit no final load.
- Existing destination mismatch, missing confirmation, production detection,
  safe logging, and dry-run tests still pass without external services.
- Record a reproducible synthetic memory comparison for increasing total row
  counts at fixed batch size. Do not claim a production memory ceiling from mocks.

## M — Measurements for deferred work

Create an opt-in offline command with deterministic synthetic inputs, no service
clients, no application server import, and no production `.env` dependency.
Measure cold/warm map indexing, row normalization/aggregation, Plotly figure
construction/serialization, and payload size at realistic sizes through the
2,000-group contract. Include overview and drilldown, aliases, unknown geography,
and Decimal totals. Record interpreter/library versions, repetitions, fixture
shape, wall times, memory measurement method, and limitations. M may also record
cache reuse/call counts and bounded ELT staging results after C/E land.

Acceptance: a documented reproducible command and baseline evidence; no flaky
timing threshold in normal CI. Do not change UI or replace Decimal to obtain a
faster number. If UI changes become necessary, read the required design skill
and project design system first; this plan authorizes no visual redesign.

For warehouse SQL, document a future operator-approved measurement checklist:
matching input selections, cache-hit state, elapsed time, bytes processed/billed,
slot-ms, JOIN output cardinality, and shuffle/spill evidence. Do not run those
queries or create monitoring/budget infrastructure in this batch. Preserve
cohort history, rolling windows, and mart/fact fallbacks until evidence supports
a particular rewrite.

## Integration checks and later review

Each worker submits an immutable commit SHA, changed files, acceptance evidence,
exact commands/results, remaining limitations, and confirmation that no live
services were used. I reviews commits serially in an integration candidate and
records conflicts/decisions. A worker's “done” is ready for review, not accepted.

Run the repository's safe full suite on the combined candidate:

```sh
uv run --locked python scripts/pre_commit_checks.py python-tests
npm run test:auth
```

Use existing Ruff/Black/mypy and other applicable staged-file hooks for changed
Python; reuse the configured Bandit hook rather than inventing scan flags:

```sh
uv run --locked pre-commit run bandit --all-files --show-diff-on-failure
npx prettier --check docs/PERFORMANCE_AUDIT_REVIEW.md docs/PERFORMANCE_IMPLEMENTATION_PLAN.md
```

Use a writable temporary `UV_CACHE_DIR` if the default cache is sandbox-blocked.
Do not weaken checks, alter dependencies, or run ELT as a test. Auth code changes
are outside C/E/M scope; if later approved, follow the full auth rebuild/check
contract in AGENTS.md. Required checks blocked by setup must be reported.

| Requirement                              | Required review evidence                                               | Accepted SHA/result                        |
| ---------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------ |
| Capacity and TTL contract                | C1 eviction/reuse tests; validated configuration; unchanged TTLs       | Passed at `58b202f`; see acceptance record |
| Same-key concurrent loads                | C2 cross-process cold/expired query-count evidence                     | Passed at `58b202f`; see acceptance record |
| Isolation and failure recovery           | All loader inputs; nested/collision/timeout cases; inventory retained  | Passed at `58b202f`; see acceptance record |
| ELT bounded extraction                   | Streaming cursor, bounded batches, synthetic memory comparison         | Passed at `58b202f`; see acceptance record |
| Complete publication                     | Read-back spool tests; one final truncate load; no partial publication | Passed at `58b202f`; see acceptance record |
| Safety and resource lifecycle            | Existing guard tests plus initialization/error cleanup cases           | Passed at `58b202f`; see acceptance record |
| Deferred bottlenecks remain evidence-led | Reproducible M results; no speculative rewrites                        | Passed at `58b202f`; see acceptance record |
| Combined regression and code quality     | Commands, results, and exact candidate SHA                             | Passed at `58b202f`; see acceptance record |

Update this table only from inspected code and executed checks. Report separately:
implemented, verified offline, integrated locally, pushed, deployed, and measured
in production. Do not mark the original audit's unsupported allegations as fixed.

Suggested request to the implementing agent:

> Implement docs/PERFORMANCE_IMPLEMENTATION_PLAN.md using parallel workers for
> tracks C, E, and M in isolated worktrees. Read docs/PERFORMANCE_AUDIT_REVIEW.md
> first, preserve existing edits, and coordinate shared-file ownership. Use only
> offline mocks and temporary resources. Submit exact commit SHAs and acceptance
> evidence for independent review; do not merge, deploy, or run live ingestion.
