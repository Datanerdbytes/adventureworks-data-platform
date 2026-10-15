# Offline performance characterization

This opt-in benchmark characterizes the existing map and bounded ELT staging. It
uses deterministic synthetic records and bundled geographic boundaries. It never
imports `app.py`, loads `.env`, creates a service client, starts a server, queries a
warehouse, or performs ingestion. It changes no UI or financial arithmetic.
Normal CI has no timing threshold.

From the repository root, after the normal locked environment setup:

```sh
uv run --locked python scripts/benchmark_performance.py --repetitions 5 > /tmp/map-baseline.json
uv run --locked python scripts/benchmark_performance.py --repetitions 5 --elt-memory > /tmp/performance-baseline.json
```

The second command requires track E's pure `elt_staging.py`. It creates only a
private temporary local Parquet spool and removes it on exit. Default synthetic
ELT counts are 10,000, 100,000 and 1,000,000, at fixed batch size 1,000; change them
with `--elt-rows` and `--batch-size`. Do not run `elt_pipeline.py` to benchmark.
Use a writable temporary `UV_CACHE_DIR` if the normal uv cache is blocked.

## What each measurement means

- `boundary_lru_cold` clears the actual one-entry `boundaries()` LRU before each
  sample, then reads and parses the bundled JSON. OS file caching stays warm;
  this does not measure a cold filesystem or process startup.
- `boundary_lru_warm` reads the populated actual boundary LRU. The existing map
  caches the JSON, not its country/state lookup indexes.
- `index_build_proxy` mirrors the current index-building loop, including aliases
  and Unicode normalization. It builds fresh indexes each time. This is a phase
  proxy, not instrumentation of time spent inside `revenue_map`.
- `aggregation_proxy` mirrors geography matching and exact Decimal accumulation
  using prebuilt indexes. It excludes geometry assembly, labels, sorting and
  Plotly construction. It includes input normalization for drilldown.
- `figure_end_to_end_warm_boundary` calls the actual `revenue_map` with warm
  boundaries, including fresh indexes, row processing, geometry assembly, styling
  and Plotly objects. Do not attribute this entire time to indexing or figure
  object construction alone. Proxy times cannot be subtracted to obtain an exact
  exclusive phase time.
- `serialization` calls the actual completed figure's `to_json()`; payload size
  is the UTF-8 byte length of that JSON. It excludes the note, Dash callback
  envelope, compression, network transfer and browser rendering.

Each phase reports median/min/max wall time using `perf_counter_ns`, with garbage
collection before each sample and no allocation tracer during timed samples.
A separate invocation records `tracemalloc` peak bytes after existing fixtures
and figure objects are allocated. This observes new traced Python allocations,
not whole-process RSS or every native allocation; peaks from different phases
cannot be added. Library imports/templates are warmed first. Shared machine load
and allocator behavior can affect timings; compare multiple fresh processes on
the same machine before interpreting differences.

## Fixture and correctness checks

Map sizes default to 100, 500 and 2,000 unique input country/state/territory groups,
matching the warehouse loader's 2,000-row return contract. The command rejects
larger sizes. It first takes up to 194 actual bundled states with canonical or
alternate names, alternating synthetic `Europe` and `Other` territory labels.
It then adds the three historical French aliases and fills remaining rows with
unique unknown states, alternating known France and unknown countries. Thus
larger fixtures intentionally stress the unmapped path; they are not a measured
production geographic distribution. The synthetic territory labels are selection
labels and do not reproduce production territory membership. There are six
bundled countries and 194 states, so 2,000 input groups do not mean 2,000 polygons.

Values are exact Decimal amounts: `100.01 + index/100` for known states and `0.10`
for aliases/unknown groups. Both overview and a `Europe` drilldown run at every
size. Assertions compare map currency labels with Decimal proxy totals, validate
unlocated-note amounts, exercise empty/all-unlocated selections, check each
historical alias resolves to a real state, and independently require alias values
`0.10 + 0.20` to produce `$0.30`. These are correctness invariants, never speed
assertions. No Decimal-to-float optimization is introduced.

The optional ELT run calls the actual pure `write_parquet_batches` helper with a
synthetic `fetchmany` source. Rows contain an int64 ID, fixed-width string label,
and Decimal amount converted according to the helper's existing float64 schema.
It verifies returned count and Parquet metadata count. Each sample regenerates
rows lazily at fixed batch size; it never prebuilds the complete input. It records
spool bytes and a separate Arrow proxy allocator peak in addition to Python
traced allocation peak. Neither allocator measurement is full process RSS; they
exclude real driver buffering, source reflection, BigQuery and other native
allocations. Parquet footer/row-group metadata grows with total row count even
when row storage is batch bounded. Variable-width production records and disk
capacity need separate operator measurements.

## Recorded baseline

Recorded 2026-10-15 from baseline `7020dd0e0c774697ba2e5f3c78e9417c28d64537`,
Python 3.12.13, `macOS-27.0.1-arm64-arm-64bit`, Plotly 6.9.0,
Dash 3.4.0, PyArrow 25.0.1; five timed repetitions plus one
separate allocation sample per operation. The ELT allocator adds one more
separate invocation. The optional helper was imported from the isolated E
worktree before integration, with SHA-256
`50b413d8f9930b95e809564ae482a50c9b50b344b4c4bb21dd7eba3bc07bcf03`.
The bundled boundaries SHA-256 was
`86187ba21c01f7b6a194607d6f9ce1bcd34f52ecd10cbad43c762019564fbd5a`.

Times below are milliseconds; brackets are observed min–max, not confidence
intervals. Timings describe this single machine/run. Full JSON includes the
same fields and exact currency totals for reproducing comparisons.

| Phase               | Median [min–max] ms    | Python traced peak bytes |
| ------------------- | ---------------------- | ------------------------ |
| `boundary_lru_cold` | 9.4686 [8.9780–9.6666] | 7,429,035                |
| `boundary_lru_warm` | 0.0005 [0.0003–0.0015] | 0                        |
| `index_build_proxy` | 0.8298 [0.8226–0.8591] | 45,928                   |

| Rows / view      | Mapped groups | Aggregation proxy ms   | Whole figure ms           | Serialization ms          | Payload bytes |
| ---------------- | ------------- | ---------------------- | ------------------------- | ------------------------- | ------------- |
| 100 / overview   | 2             | 0.0382 [0.0372–0.0452] | 11.5478 [11.3103–11.6749] | 3.3156 [3.2754–5.0325]    | 61,924        |
| 100 / Europe     | 50            | 0.1190 [0.1160–0.1229] | 22.0882 [20.8694–22.3573] | 18.7480 [18.5862–18.7921] | 274,161       |
| 500 / overview   | 2             | 0.1512 [0.1499–0.1537] | 11.6049 [11.4564–11.6462] | 3.3566 [3.3081–3.4345]    | 62,795        |
| 500 / Europe     | 99            | 0.7764 [0.7690–0.7991] | 23.3962 [23.2898–23.8952] | 21.5010 [21.4555–21.9776] | 315,978       |
| 2,000 / overview | 2             | 0.5431 [0.5323–0.5955] | 12.1112 [12.0288–12.1594] | 3.3894 [3.3768–3.4120]    | 62,795        |
| 2,000 / Europe   | 99            | 3.6141 [3.5393–3.6620] | 26.3740 [26.1605–26.6169] | 21.5839 [21.4876–21.8114] | 315,978       |

| Rows / view      | Aggregation / figure / serialization Python traced peak bytes |
| ---------------- | ------------------------------------------------------------- |
| 100 / overview   | 854 / 573,376 / 385,727                                       |
| 100 / Europe     | 8,606 / 2,983,267 / 2,777,080                                 |
| 500 / overview   | 854 / 560,960 / 394,036                                       |
| 500 / Europe     | 15,560 / 3,337,892 / 3,103,888                                |
| 2,000 / overview | 854 / 560,848 / 394,036                                       |
| 2,000 / Europe   | 15,562 / 3,337,892 / 3,103,888                                |

| ELT rows (batch 1,000) | Stage ms                        | Python traced peak bytes | Arrow allocator peak bytes | Spool bytes |
| ---------------------- | ------------------------------- | ------------------------ | -------------------------- | ----------- |
| 10,000                 | 11.8355 [11.7353–224.1347]      | 651,665                  | 36,224                     | 122,164     |
| 100,000                | 135.8833 [133.9775–136.7512]    | 651,537                  | 36,224                     | 1,217,928   |
| 1,000,000              | 1267.9229 [1258.4198–1383.0511] | 651,409                  | 36,224                     | 12,182,501  |

The first ELT timing includes lazy Arrow conversion initialization, explaining
its wide min–max range. Bounded batch allocations stay approximately level in
these two allocator measurements while disk usage grows with input size. This
does not prove that full process memory is constant: native Parquet metadata and
a real PostgreSQL driver are outside those allocator observations. Map index
building is a small component in this fixture; the result does not justify a
production optimization or a severity claim.

## Future warehouse measurement checklist

This batch runs no SQL measurements. A separately approved operator session
should compare the same report, year/quarter/channel/category/subcategory,
dimension and dataset selections, preserving cohort history, rolling windows and
mart/fact fallbacks. For each baseline/candidate pair, record:

1. Application cache hit/miss state and BigQuery job cache-hit state separately.
2. Elapsed query and end-to-end report time, bytes processed/billed and slot-ms.
3. Execution-stage input/output rows, JOIN output cardinality, shuffle bytes and
   disk spill evidence; identify the stage responsible for a change.
4. Equivalent returned rows and financial totals, identical billing limits,
   timeouts and input data snapshots, plus repetitions and concurrent workload.

Keep query identifiers and aggregate statistics free of credentials. A changed
query text or repeated CTE does not establish quadratic complexity, duplicate
execution, or a measured bottleneck. These offline map/ELT results establish no
production p95, warehouse costs, concurrency capacity or deployment state.
