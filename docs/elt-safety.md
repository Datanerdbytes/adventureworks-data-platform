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
