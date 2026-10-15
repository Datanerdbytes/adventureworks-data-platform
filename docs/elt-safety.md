# ELT safety checks

The pipeline replaces the fixed AdventureWorks destination tables using
`WRITE_TRUNCATE`. It does not change IAM or grant permission to write.

## Destination validation

Set `GBQ_PROJECT_ID` to the canonical Google Cloud project ID. Project numbers,
whitespace, and malformed IDs are rejected, preventing numeric aliases from
bypassing the production project check. `GBQ_DATASET_ID` accepts a dataset ID or
`project.dataset` with the same project. Dataset IDs may contain ASCII letters,
numbers, and underscores, up to 1,024 characters. Empty components, additional
dots, conflicting prefixes, paths, and surrounding whitespace are rejected before
creating clients or reading source data.

Identifier checks follow the [Google Cloud project ID rules](https://docs.cloud.google.com/resource-manager/docs/creating-managing-projects)
and [BigQuery dataset naming rules](https://docs.cloud.google.com/bigquery/docs/datasets).
Environment variables take precedence over local `.env` settings.

## Preflight and execution

Run a side-effect-free preflight first:

```sh
python elt_pipeline.py --dry-run
```

Production writes require both `--confirm-production` and
`--destination <exact-project.dataset>`. This applies to interactive shells and
noninteractive jobs; the pipeline never auto-answers prompts. The known production
project is recognized even when `ENVIRONMENT` says development. Software checks
supplement, and do not replace, the repository's required multi-turn human approval.
Do not execute a real production migration without that separate approval.

For the callable API, `dry_run` and `confirm_production` must be actual Python
booleans. `interactive` must be a boolean or `None`; `destination` must be a valid
`project.dataset` string or `None`. Strings such as `"false"` and numeric values
such as `1` are rejected. A supplied destination must match the resolved target
before execution, including on nonproduction projects.

## Failure output

Configuration/confirmation failures exit with status 2. Operational and partial
migration failures exit with status 1. Output uses fixed operational error
categories and the fixed table names, without raw exception messages, SQL, data
rows, or connection URLs. A partial failure still reports the failed table list.
It does not roll back tables that were successfully replaced earlier in the run.

## Offline verification

The tests mock PostgreSQL and BigQuery, including explicitly confirmed production
execution. They verify exact table destinations, `WRITE_TRUNCATE`, the existing
`asia-east2` region, malformed configuration, option types, dry-run isolation,
nonzero failure exits, and suppression of synthetic secrets in errors. Do not run
the real pipeline as a validation step.

## Bounded extraction and staged publication

The pipeline requests SQLAlchemy server-side streaming with `stream_results`,
`yield_per`, and `max_row_buffer`, then consumes `fetchmany` batches. The default
is 10,000 rows; `--batch-size` (or callable `batch_size`) accepts integers from 1
through 100,000. Validation occurs before clients and temporary exports, including
in dry-run mode. A row count limit does not bound bytes in unusually large cells.

Each table is written incrementally into a private temporary Parquet spool. The
source result and connection close before upload. Only after every batch and the
Parquet footer succeed does the pipeline submit **one** file load with
`WRITE_TRUNCATE` and wait for its completion. Extraction, conversion, and disk
errors submit no replacement for that table. Empty tables still skip upload and
leave the destination unchanged. Failed final jobs are reported as failed, with a
nonzero final exit; earlier successful tables are not rolled back.

Schema comes from PostgreSQL column metadata, not the first batch. Nullable
integers and booleans, dates, timestamps (including UTC-normalized timezone-aware
values), times without timezones, strings, binary values, and UUIDs have explicit
Arrow types. The file load supplies an explicit BigQuery schema derived from
the closed spool metadata, retaining naive timestamps as `DATETIME` and
timezone-aware timestamps as `TIMESTAMP` rather than relying on Parquet
autodetection. Unsupported source types fail the table safely before publication.
Numeric/Decimal values intentionally remain float64, preserving the prior
pipeline's Decimal-to-float conversion and its precision limitation. This change
does not introduce a lossless financial export. The typed nullable integer schema
also avoids pandas' incidental integer-to-float inference when a column has nulls.

Disk usage grows with the size of one table; plan temporary storage accordingly
(`TMPDIR` selects the standard Python temporary location). Disk exhaustion while
writing batches or the footer fails the table before upload. Row data is bounded
by batch size, while Parquet row-group metadata grows with batch count. This is
not a strict constant-memory or production memory-ceiling guarantee.

Results, source connections, writers, temporary exports, the BigQuery client, and
the engine are closed or removed on success and failure, including BigQuery
client initialization failure after engine creation. Cleanup errors do not mask
an earlier operational failure. A temporary export removal failure prints a fixed
warning requiring operator cleanup, without exposing row data or filesystem
paths. Abrupt process termination or host failure can leave a spool behind;
operators should retain normal temporary-directory hygiene.

Offline regression tests read the actual Parquet file at the fake upload
boundary, verify every row and type across batches (including an all-null first
batch), reject `fetchall`, and verify batch-reference release, cursor options,
empty-table behavior, failure publication boundaries, and lifecycle cleanup.
Synthetic increasing-size memory characterization is documented in
[the offline benchmark](performance-benchmark.md); it does not establish live
driver buffering behavior, warehouse performance, or production capacity.
