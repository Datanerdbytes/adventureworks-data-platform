# Separate legacy records from live accounts

**Applied to hosted Supabase on 2026-10-19 with explicit user authorization.**
All seven named references, both original safety guards, both lifecycle triggers,
private registry permissions and the protected owner were verified before commit.
All Auth account states and all workspace/membership/request/approval/audit rows
were compared before and after migration and preserved. No account deletion was
attempted. Permanent account deletion remains a deliberate, separately confirmed
action in User Management. Workspace cutover migration 0004 was not applied.

## Problem and behavior

Legacy workspace tables reference `auth.users` with restrictive foreign keys.
Those references block permanent deletion of an otherwise eligible suspended
member. Deleting the workspace rows would discard membership and audit history;
setting identifiers to NULL would also conflict with existing primary keys,
required actors and reviewed-request checks.

Migration `202610190005_legacy_account_history.sql` instead creates a private
UUID-only identity-history table and retargets seven explicitly named references:

| Legacy table                | Retained account references |
| --------------------------- | --------------------------- |
| `workspace_memberships`     | `user_id`                   |
| `platform_administrators`   | `user_id`                   |
| `workspace_approvals`       | `approved_by`, `claimed_by` |
| `workspace_access_requests` | `user_id`, `reviewed_by`    |
| `governance_audit_events`   | `actor_id`                  |

Every existing legacy row, UUID, status, role, timestamp and event detail remains
unchanged. The private registry contains `user_id` and `deleted_at`, with no email,
credentials, tokens or copied Auth metadata. Existing legacy records may already
contain emails or other details, and those are retained. This migration separates
sign-in account deletion from history retention; it is not an anonymization or
complete personal-data-erasure operation.

New Auth inserts register their identity before existing confirmation/approval
triggers run. Successful Auth deletions mark the retained identity as deleted in
the same transaction. A failed Auth write rolls back its registry write. A deleted
UUID cannot be reused to inherit old membership or platform-administrator rows.
Registering the same email with a new UUID creates a separate identity.

The registry and trigger functions are private: browser roles and `service_role`
have no direct read/write/execute grants. Security-definer lifecycle triggers
maintain the registry. Legacy role rows are historical evidence, not current
account authorization; current access still requires a confirmed, active account.

## Boundaries

The existing owner/admin/suspension deletion guard remains unchanged. Only the
protected owner can delete a suspended non-admin through the application, after
typing its current email. The migration does not remove files, cascade-delete
workspace/audit records, enable lockout, change email/OAuth configuration, grant
account privileges or retry a failed account deletion.

Storage ownership checks and all unrelated foreign keys remain blocking. New
references from another application are not automatically detached. Refresh the
directory before any deliberate deletion retry, because an earlier timeout may
have an uncertain outcome.

## Installation review

Requires the historical governance tables plus installed and enabled safety
migrations `202610190001`–`202610190003`. It can run before or after workspace
cutover migration `202610190004`; it does not install or authorize that cutover.
Do not run a blanket push of all pending migrations just to install this file if
the old live application still depends on migration 0004's retired permissions.

Before applying, review a current backup, the exact project/connection, the named
constraints and any additional account references or Storage ownership. Use
verified TLS and the operator connection, never browser credentials or a web
service database URL. The operator needs the relevant table/trigger privileges.
Use a brief maintenance window: the transaction locks Auth and the five legacy
tables to prevent a backfill/write race. A five-second lock timeout fails rather
than waiting indefinitely. Missing/disabled guards, unexpected constraint names
or any SQL failure roll back the entire migration.

Apply this exact migration only with explicit hosted authorization. Verify the
seven references point at the private registry, browser/service direct access is
denied and both original safety guards are still ready. Verify preserved row
counts and existing account flags without deleting a real account as a test.

Before any account has been deleted, a separately reviewed rollback can restore
the original references. After a deletion, restoring foreign keys to `auth.users`
will fail for retained history without a deliberate data-recovery/archival plan.
Do not erase history or create replacement sign-in accounts to force rollback.

## Isolated verification

The tests use synthetic accounts and the actual historical migrations in PGlite.
They cover unchanged historical values, deletion eligibility, a new registration
and confirmation queue, same-email/new-UUID separation, UUID-reuse denial,
private-registry permissions, unrelated constraint blocking, safety-guard refusal,
installation before/after cutover, and rollback on an unexpected schema.

```sh
QE_PGLITE_MODULE=/absolute/path/to/pglite/dist/index.js node --test supabase/tests/legacy-account-history.test.mjs
```

No hosted database, provider request, email delivery or real account is used.
