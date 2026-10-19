// Optional isolated PostgreSQL regression suite. No network or hosted database.
// QE_PGLITE_MODULE can point at a temporary @electric-sql/pglite installation.
import { test, before, beforeEach, after } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const { PGlite } = await import(
  process.env.QE_PGLITE_MODULE || "@electric-sql/pglite"
);
let db;
before(async () => {
  db = new PGlite();
  await db.exec(`create role anon; create role authenticated; create role service_role;
    create schema auth; create table auth.users(id uuid primary key, email text, encrypted_password text, raw_app_meta_data jsonb default '{}', banned_until timestamptz, email_confirmed_at timestamptz default now());`);
  await db.exec(
    readFileSync(
      "supabase/migrations/202610190001_password_lockout.sql",
      "utf8",
    ),
  );
  await db.exec(
    readFileSync(
      "supabase/migrations/202610190002_account_deletion_guard.sql",
      "utf8",
    ),
  );
  await db.exec(
    readFileSync(
      "supabase/migrations/202610190003_administrator_access_guard.sql",
      "utf8",
    ),
  );
});
beforeEach(async () =>
  db.exec(
    "truncate public.qe_password_attempts, public.qe_protected_owner, auth.users;",
  ),
);
after(async () => db?.close());
async function attempt(
  action,
  valid = null,
  lease = null,
  email = "person@example.com",
) {
  const { rows } = await db.query(
    "select public.qe_password_attempt($1,$2,$3,$4) as result",
    [email, action, lease, valid],
  );
  return rows[0].result;
}
async function fail(email) {
  const start = await attempt("start", null, null, email);
  assert.equal(start.allowed, true);
  return attempt("finish", false, start.attempt_id, email);
}
test("fifth incorrect password locks; correct password cannot bypass an active lock", async () => {
  for (let i = 0; i < 4; i++)
    assert.equal((await fail()).error, "invalid_credentials");
  assert.equal((await fail()).error, "account_locked");
  const start = await attempt("start");
  assert.equal(start.allowed, false);
  assert.equal(start.retry_after, 900);
  assert.equal((await attempt("status")).error, "account_locked");
  assert.equal(
    (await attempt("finish", true, "11111111-1111-4111-8111-111111111111"))
      .error,
    "account_locked",
  );
});
test("expired lock unlocks and starts a fresh failure window", async () => {
  for (let i = 0; i < 5; i++) await fail();
  await db.exec(
    "update public.qe_password_attempts set locked_until=clock_timestamp()-interval '1 second';",
  );
  assert.equal((await attempt("status")).allowed, true);
  assert.equal((await fail()).error, "invalid_credentials");
  const { rows } = await db.query(
    "select failures from public.qe_password_attempts",
  );
  assert.equal(rows[0].failures, 1);
});
test("successful password clears accumulated failures", async () => {
  for (let i = 0; i < 4; i++) await fail();
  const start = await attempt("start");
  assert.equal((await attempt("finish", true, start.attempt_id)).allowed, true);
  const { rows } = await db.query(
    "select failures from public.qe_password_attempts",
  );
  assert.equal(rows[0].failures, 0);
  assert.equal((await fail()).error, "invalid_credentials");
});
test("failure window expires independently of the lock", async () => {
  for (let i = 0; i < 4; i++) await fail();
  await db.exec(
    "update public.qe_password_attempts set window_started_at=clock_timestamp()-interval '16 minutes';",
  );
  await fail();
  const { rows } = await db.query(
    "select failures from public.qe_password_attempts",
  );
  assert.equal(rows[0].failures, 1);
});
test("parallel attempts share one lease and cannot undercount", async () => {
  const starts = await Promise.all(
    Array.from({ length: 8 }, () => attempt("start")),
  );
  assert.equal(starts.filter((s) => s.allowed).length, 1);
  assert.equal(
    starts.filter((s) => s.error === "attempt_in_progress").length,
    7,
  );
  const lease = starts.find((s) => s.allowed).attempt_id;
  await attempt("finish", false, lease);
  assert.equal((await attempt("finish", true, lease)).error, "attempt_expired");
});
test("crashed or delayed attempts expire and cannot finalize a newer lease", async () => {
  const old = await attempt("start");
  await db.exec(
    "update public.qe_password_attempts set attempt_expires_at=clock_timestamp()-interval '1 second';",
  );
  const current = await attempt("start");
  assert.notEqual(old.attempt_id, current.attempt_id);
  assert.equal(
    (await attempt("finish", true, old.attempt_id)).error,
    "attempt_expired",
  );
  assert.equal(
    (await attempt("finish", true, current.attempt_id)).allowed,
    true,
  );
});
test("service failures release the lease without counting incorrect passwords", async () => {
  const start = await attempt("start");
  await attempt("finish", null, start.attempt_id);
  const { rows } = await db.query(
    "select failures,attempt_id from public.qe_password_attempts",
  );
  assert.equal(rows[0].failures, 0);
  assert.equal(rows[0].attempt_id, null);
});
test("normalization shares counters and unrelated accounts remain available", async () => {
  for (let i = 0; i < 5; i++) await fail("PERSON@example.com ");
  assert.equal(
    (await attempt("status", null, null, " person@EXAMPLE.COM")).error,
    "account_locked",
  );
  assert.equal(
    (await attempt("start", null, null, "other@example.com")).allowed,
    true,
  );
});
test("only changing password hash clears the lock", async () => {
  for (let i = 0; i < 5; i++) await fail();
  await db.exec(
    "insert into auth.users(id,email,encrypted_password) values('11111111-1111-4111-8111-111111111111','person@example.com','old-hash'); update auth.users set encrypted_password='old-hash';", // pragma: allowlist secret (synthetic test data or non-secret feature flag)
  );
  assert.equal((await attempt("status")).error, "account_locked");
  await db.exec("update auth.users set encrypted_password='new-hash';"); // pragma: allowlist secret (synthetic test data or non-secret feature flag)
  assert.equal((await attempt("status")).allowed, true);
});
test("browser roles cannot read counters or call privileged RPC", async () => {
  for (const role of ["anon", "authenticated"]) {
    await db.exec(`set role ${role}`);
    try {
      await assert.rejects(
        db.query("select * from public.qe_password_attempts"),
        /permission denied/,
      );
      await assert.rejects(attempt("start"), /permission denied/);
      await assert.rejects(guardReady(), /permission denied/);
    } finally {
      await db.exec("reset role");
    }
  }
  await db.exec("set role service_role");
  try {
    assert.equal((await attempt("start")).allowed, true);
  } finally {
    await db.exec("reset role");
  }
});

async function guardReady() {
  return (
    await db.query("select public.qe_account_deletion_guard_ready() as result")
  ).rows[0].result.ready;
}
async function member(metadata = {}, bannedUntil = null) {
  await db.query(
    "insert into auth.users(id,email,raw_app_meta_data,banned_until) values ('22222222-2222-4222-8222-222222222222','member@example.com',$1,$2)",
    [JSON.stringify(metadata), bannedUntil],
  );
}
test("deletion guard rejects a concurrent restoration or promotion after selection", async () => {
  for (const change of [
    "raw_app_meta_data='{}', banned_until=null",
    `raw_app_meta_data='{"qe_role":"admin"}', banned_until=null`,
  ]) {
    await db.exec("truncate auth.users");
    await member({ qe_suspended: true });
    const selected = (await db.query("select * from auth.users")).rows[0];
    assert.equal(selected.raw_app_meta_data.qe_suspended, true);
    await db.exec(`update auth.users set ${change}`);
    await assert.rejects(
      db.exec("delete from auth.users"),
      /Only suspended non-administrator/,
    );
    assert.equal(
      (await db.query("select count(*) as total from auth.users")).rows[0]
        .total,
      1,
    );
  }
});
test("database guard protects owners and admins even if suspended", async () => {
  for (const metadata of [
    { qe_owner: true, qe_suspended: true },
    { qe_role: "admin", qe_suspended: true },
    {},
  ]) {
    await db.exec("truncate auth.users");
    await member({ qe_suspended: true });
    // Model a pre-existing protected or inconsistent account while testing deletion.
    await db.exec(
      "alter table auth.users disable trigger qe_guard_administrator_access",
    );
    try {
      await db.query("update auth.users set raw_app_meta_data=$1", [
        JSON.stringify(metadata),
      ]);
    } finally {
      await db.exec(
        "alter table auth.users enable trigger qe_guard_administrator_access",
      );
    }
    await assert.rejects(
      db.exec("delete from auth.users"),
      /Only suspended non-administrator/,
    );
  }
});
test("database guard permits only currently suspended members", async () => {
  await member({ qe_suspended: true });
  await db.exec("delete from auth.users");
  await member({}, "2099-01-01T00:00:00Z");
  await db.exec("delete from auth.users");
  assert.equal(
    (await db.query("select count(*) as total from auth.users")).rows[0].total,
    0,
  );
});
test("disabled deletion triggers are detected before provider deletion", async () => {
  assert.equal(await guardReady(), true);
  await db.exec(
    "alter table auth.users disable trigger qe_guard_account_deletion",
  );
  try {
    assert.equal(await guardReady(), false);
  } finally {
    await db.exec(
      "alter table auth.users enable trigger qe_guard_account_deletion",
    );
  }
});

test("parallel promotion and suspension cannot leave a suspended administrator", async () => {
  await member({});
  await db.exec(
    `update auth.users set raw_app_meta_data='{"qe_role":"admin"}'`,
  );
  await assert.rejects(
    db.exec(
      `update auth.users set raw_app_meta_data='{"qe_role":"admin","qe_suspended":true}'`,
    ),
    /Revoke administrator access/,
  );
  await assert.rejects(
    db.exec(`update auth.users set banned_until='2099-01-01'`),
    /Revoke administrator access/,
  );
  await db.exec(
    `update auth.users set raw_app_meta_data='{"qe_role":"member","qe_suspended":true}', banned_until='2099-01-01'`,
  );
  await assert.rejects(
    db.exec(
      `update auth.users set raw_app_meta_data='{"qe_role":"admin","qe_suspended":true}'`,
    ),
    /Revoke administrator access/,
  );
  await db.exec(
    `update auth.users set raw_app_meta_data='{}', banned_until=null`,
  );
  await db.exec(
    `update auth.users set raw_app_meta_data='{"qe_role":"admin"}'`,
  );
});

test("owner cannot be demoted and a second owner cannot be bootstrapped", async () => {
  await member({ qe_role: "admin", qe_owner: true });
  await assert.rejects(
    db.exec(
      `update auth.users set raw_app_meta_data='{"qe_role":"member","qe_owner":true}'`,
    ),
    /initial owner is protected/,
  );
  await assert.rejects(
    db.exec(`update auth.users set raw_app_meta_data='{"qe_role":"admin"}'`),
    /initial owner is protected/,
  );
  await assert.rejects(
    db.exec(
      `insert into auth.users(id,email,email_confirmed_at,raw_app_meta_data) values ('33333333-3333-4333-8333-333333333333','second@example.test',now(),'{"qe_role":"admin","qe_owner":true}')`,
    ),
    /different initial owner already exists/,
  );
});

test("database rejects promotion when verification changed after selection", async () => {
  await member({});
  await db.exec("update auth.users set email_confirmed_at=null");
  await assert.rejects(
    db.exec(`update auth.users set raw_app_meta_data='{"qe_role":"admin"}'`),
    /email must be verified/,
  );
});

test("administrator guard readiness detects a disabled trigger and denies browser calls", async () => {
  const ready = async () =>
    (await db.query("select public.qe_administrator_guard_ready() as result"))
      .rows[0].result.ready;
  assert.equal(await ready(), true);
  await db.exec(
    "alter table auth.users disable trigger qe_guard_administrator_access",
  );
  try {
    assert.equal(await ready(), false);
  } finally {
    await db.exec(
      "alter table auth.users enable trigger qe_guard_administrator_access",
    );
  }
  await db.exec("set role authenticated");
  try {
    await assert.rejects(ready(), /permission denied/);
  } finally {
    await db.exec("reset role");
  }
});

test("cutover revokes legacy RPC and table access while preserving data and email-first registration", async () => {
  // Separate synthetic database representing the existing governance installation.
  const legacy = new PGlite();
  try {
    await legacy.exec(`create role anon; create role authenticated; create schema auth; create schema governance_private;
      create table auth.users(id uuid primary key,raw_app_meta_data jsonb,email_confirmed_at timestamptz);
      create table public.workspaces(id integer); insert into public.workspaces values(7);
      create table public.workspace_memberships(id integer); create table public.workspace_access_requests(id integer);
      create table public.workspace_approvals(id integer); create table public.governance_audit_events(id integer);
      create table public.platform_administrators(id integer);
      grant select on public.workspaces to authenticated;
      create function public.workspace_context() returns jsonb language sql as $$ select '{}'::jsonb $$;
      grant execute on function public.workspace_context() to anon,authenticated;
      create function governance_private.queue_verified_registration() returns trigger language plpgsql as $$ begin return new; end $$;
      create trigger queue_verified_registration after insert on auth.users for each row execute function governance_private.queue_verified_registration();
    `);
    await legacy.exec(
      readFileSync(
        "supabase/migrations/202610190004_retire_workspace_access.sql",
        "utf8",
      ),
    );
    assert.equal(
      (await legacy.query("select * from public.workspaces")).rows[0].id,
      7,
    );
    assert.equal(
      (
        await legacy.query(
          "select count(*) as total from pg_trigger where tgname='queue_verified_registration'",
        )
      ).rows[0].total,
      0,
    );
    await legacy.exec("set role authenticated");
    await assert.rejects(
      legacy.exec("select * from public.workspaces"),
      /permission denied/,
    );
    await assert.rejects(
      legacy.exec("select public.workspace_context()"),
      /permission denied/,
    );
    await legacy.exec("reset role");
    await assert.rejects(
      legacy.exec(
        `insert into auth.users values ('44444444-4444-4444-8444-444444444444','{"provider":"google"}',now())`,
      ),
      /Create and verify an email/,
    );
    await legacy.exec(
      `insert into auth.users values ('44444444-4444-4444-8444-444444444444','{"provider":"email"}',now())`,
    );
  } finally {
    await legacy.close();
  }
});

test("owner registry is private to the guard and rolls back with a failed Auth insert", async () => {
  for (const role of ["anon", "authenticated", "service_role"]) {
    await db.exec(`set role ${role}`);
    try {
      await assert.rejects(
        db.exec("select * from public.qe_protected_owner"),
        /permission denied/,
      );
    } finally {
      await db.exec("reset role");
    }
  }
  await member({});
  await assert.rejects(
    db.exec(
      `insert into auth.users(id,email,raw_app_meta_data) values ('22222222-2222-4222-8222-222222222222','duplicate@example.test','{"qe_role":"admin","qe_owner":true}')`,
    ),
    /duplicate key/,
  );
  assert.equal(
    (await db.query("select count(*) as total from public.qe_protected_owner"))
      .rows[0].total,
    0,
  );
});
