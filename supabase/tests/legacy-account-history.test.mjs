// Isolated PostgreSQL only: no hosted SQL, provider calls or real accounts.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
const { PGlite } = await import(
  process.env.QE_PGLITE_MODULE || "@electric-sql/pglite"
);
const OWNER = "11111111-1111-4111-8111-111111111111";
const MEMBER = "22222222-2222-4222-8222-222222222222";
const NEW = "33333333-3333-4333-8333-333333333333";
const WORKSPACE = "44444444-4444-4444-8444-444444444444";
const migration = readFileSync(
  "supabase/migrations/202610190005_legacy_account_history.sql",
  "utf8",
);
test("shared Auth stub supports legacy checks followed by the complete account cutover", async () => {
  const db = new PGlite();
  const run = (file) =>
    db.exec(readFileSync(file, "utf8").replace(/^\\.*$/gm, ""));
  const files = readdirSync("supabase/migrations")
    .filter((file) => file.endsWith(".sql"))
    .sort();
  try {
    await run("supabase/tests/auth_stub.sql");
    for (const file of files.slice(0, 3))
      await run("supabase/migrations/" + file);
    await run("supabase/tests/governance.sql");
    await run("supabase/tests/registration.sql");
    await db.exec(`insert into auth.users(id,email,email_confirmed_at)
      values('a0000000-0000-0000-0000-000000000099','legacy-pending@example.test',now());
      set role authenticated;
      select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000002',false);
      select public.approve_workspace_email('10000000-0000-0000-0000-000000000001','legacy-pending@example.test','viewer');
      reset role;`);
    for (const file of files.slice(3).filter((file) => file < "202610190004"))
      await run("supabase/migrations/" + file);
    for (const file of [
      "access_requests.sql",
      "password_lockout.sql",
      "admin_directory_activity.sql",
    ])
      await run("supabase/tests/" + file);
    await db.exec(`reset role;
      create temporary table legacy_cutover_snapshot as select
      (select count(*) from public.workspaces) as workspaces,
      (select count(*) from public.workspace_memberships) as memberships,
      (select count(*) from public.governance_audit_events) as events;`);
    for (const file of files.filter((file) => file >= "202610190004"))
      await run("supabase/migrations/" + file);
    await run("supabase/tests/account_cutover.sql");
  } finally {
    await db.close();
  }
});
async function setup() {
  const db = new PGlite();
  await db.exec(readFileSync("supabase/tests/auth_stub.sql", "utf8"));
  for (const file of readdirSync("supabase/migrations").sort()) {
    if (file.endsWith(".sql") && file < "202610190004")
      await db.exec(readFileSync("supabase/migrations/" + file, "utf8"));
  }
  await db.query(
    `insert into auth.users(id,email,email_confirmed_at,raw_app_meta_data) values
  ($1,'owner@example.test',now(),'{"provider":"email","qe_role":"admin","qe_owner":true}'),
  ($2,'member@example.test',now(),'{"provider":"email","qe_suspended":true}')`,
    [OWNER, MEMBER],
  );
  await db.query(
    "insert into public.workspaces(id,name,purpose,responsible_team) values($1,'Historical workspace','Reporting','Analytics')",
    [WORKSPACE],
  );
  await db.query(
    "insert into public.workspace_memberships(workspace_id,user_id,role) values($1,$2,'viewer')",
    [WORKSPACE, MEMBER],
  );
  await db.query(
    "insert into public.platform_administrators(user_id) values($1)",
    [MEMBER],
  );
  await db.query(
    "insert into public.workspace_approvals(workspace_id,email,role,status,claimed_by,approved_by) values($1,'member@example.test','viewer','claimed',$2,$2)",
    [WORKSPACE, MEMBER],
  );
  await db.query(
    "insert into public.workspace_access_requests(workspace_id,user_id,status,reviewed_by,reviewed_at,granted_role) values($1,$2,'approved',$2,now(),'viewer')",
    [WORKSPACE, MEMBER],
  );
  await db.query(
    "insert into public.governance_audit_events(workspace_id,actor_id,action,target_id,details) values($1,$2,'legacy_action',$2,'{\"retained\":true}')",
    [WORKSPACE, MEMBER],
  );
  return db;
}
async function history(db) {
  const result = {};
  for (const table of [
    "workspace_memberships",
    "platform_administrators",
    "workspace_approvals",
    "workspace_access_requests",
    "governance_audit_events",
  ])
    result[table] = (await db.query("select * from public." + table)).rows;
  return result;
}
test("separation preserves every historical value while allowing an eligible account deletion", async () => {
  const db = await setup();
  try {
    const before = await history(db);
    await assert.rejects(
      db.query("delete from auth.users where id=$1", [MEMBER]),
      /foreign key/,
    );
    await db.exec(migration);
    assert.deepEqual(await history(db), before);
    await db.query("delete from auth.users where id=$1", [MEMBER]);
    assert.deepEqual(await history(db), before);
    assert.equal(
      (
        await db.query("select count(*) as n from auth.users where id=$1", [
          MEMBER,
        ])
      ).rows[0].n,
      0,
    );
    assert(
      (
        await db.query(
          "select deleted_at from governance_private.account_history_identities where user_id=$1",
          [MEMBER],
        )
      ).rows[0].deleted_at,
    );
    // Current governance still requires an actual verified Auth account.
    await db.exec("set role authenticated");
    await db.query("select set_config('request.jwt.claim.sub',$1,false)", [
      MEMBER,
    ]);
    await assert.rejects(
      db.exec("select public.workspace_context()"),
      /Confirmed authentication required/,
    );
    await db.exec("reset role");
  } finally {
    await db.close();
  }
});
test("new registrations work; same email with a new ID never inherits historical membership", async () => {
  const db = await setup();
  try {
    await db.exec(migration);
    await db.query("delete from auth.users where id=$1", [MEMBER]);
    await assert.rejects(
      db.query(
        "insert into auth.users(id,email,raw_app_meta_data) values($1,'reuse@example.test','{\"provider\":\"email\"}')",
        [MEMBER],
      ),
      /historical identity cannot be reused/,
    );
    await db.query(
      "insert into auth.users(id,email,email_confirmed_at,raw_app_meta_data) values($1,'member@example.test',now(),'{\"provider\":\"email\"}')",
      [NEW],
    );
    assert.equal(
      (
        await db.query(
          "select deleted_at from governance_private.account_history_identities where user_id=$1",
          [NEW],
        )
      ).rows[0].deleted_at,
      null,
    );
    assert.equal(
      (
        await db.query(
          "select count(*) as n from public.workspace_memberships where user_id=$1",
          [NEW],
        )
      ).rows[0].n,
      0,
    );
    // Confirmation queue writes can reference the identity created by BEFORE INSERT.
    await db.query(
      "update public.workspaces set registration_default=true where id=$1",
      [WORKSPACE],
    );
    const another = "55555555-5555-4555-8555-555555555555";
    await db.query(
      "insert into auth.users(id,email,email_confirmed_at) values($1,'new@example.test',now())",
      [another],
    );
    assert.equal(
      (
        await db.query(
          "select count(*) as n from public.workspace_access_requests where user_id=$1",
          [another],
        )
      ).rows[0].n,
      1,
    );
  } finally {
    await db.close();
  }
});
test("owner/admin/active-account guards and unrelated foreign keys still block deletion", async () => {
  const db = await setup();
  try {
    await db.exec(migration);
    await assert.rejects(
      db.query("delete from auth.users where id=$1", [OWNER]),
      /Only suspended non-administrator/,
    );
    await db.query(
      'insert into auth.users(id,email,email_confirmed_at,raw_app_meta_data) values($1,\'active@example.test\',now(),\'{"provider":"email","qe_role":"admin"}\')',
      [NEW],
    );
    await assert.rejects(
      db.query("delete from auth.users where id=$1", [NEW]),
      /Only suspended non-administrator/,
    );
    await db.query(
      'update auth.users set raw_app_meta_data=\'{"provider":"email"}\' where id=$1',
      [NEW],
    );
    await assert.rejects(
      db.query("delete from auth.users where id=$1", [NEW]),
      /Only suspended non-administrator/,
    );
    await db.exec(
      "create table public.unrelated_records(user_id uuid references auth.users(id))",
    );
    await db.query("insert into public.unrelated_records values($1)", [MEMBER]);
    await assert.rejects(
      db.query("delete from auth.users where id=$1", [MEMBER]),
      /foreign key/,
    );
    assert.equal(
      (
        await db.query(
          "select deleted_at from governance_private.account_history_identities where user_id=$1",
          [MEMBER],
        )
      ).rows[0].deleted_at,
      null,
    );
  } finally {
    await db.close();
  }
});
test("history registry stays private and rejects invented legacy identities", async () => {
  const db = await setup();
  try {
    await db.exec(migration);
    for (const role of ["anon", "authenticated", "service_role"]) {
      await db.exec("set role " + role);
      try {
        await assert.rejects(
          db.exec(
            "select * from governance_private.account_history_identities",
          ),
          /permission denied/,
        );
        await assert.rejects(
          db.query(
            "insert into governance_private.account_history_identities(user_id) values($1)",
            [NEW],
          ),
          /permission denied/,
        );
      } finally {
        await db.exec("reset role");
      }
    }
    await assert.rejects(
      db.query(
        "insert into public.workspace_memberships(workspace_id,user_id,role) values($1,$2,'viewer')",
        [WORKSPACE, NEW],
      ),
      /foreign key/,
    );
  } finally {
    await db.close();
  }
});
test("preflight refuses to separate history if an existing safety guard is disabled", async () => {
  const db = await setup();
  try {
    await db.exec(
      "alter table auth.users disable trigger qe_guard_account_deletion",
    );
    await assert.rejects(
      db.exec(migration),
      /Install and enable the account safety guards/,
    );
    await db.exec("rollback");
    assert.equal(
      (
        await db.query(
          "select to_regclass('governance_private.account_history_identities') as relation",
        )
      ).rows[0].relation,
      null,
    );
  } finally {
    await db.close();
  }
});

test("separation also works after the independently scheduled workspace cutover", async () => {
  const db = await setup();
  try {
    const before = await history(db);
    await db.exec(
      readFileSync(
        "supabase/migrations/202610190004_retire_workspace_access.sql",
        "utf8",
      ),
    );
    await db.exec(migration);
    await db.query("delete from auth.users where id=$1", [MEMBER]);
    assert.deepEqual(await history(db), before);
  } finally {
    await db.close();
  }
});
test("unexpected legacy schema rolls back the entire migration rather than partially detaching records", async () => {
  const db = await setup();
  try {
    await db.exec(
      "alter table public.governance_audit_events rename constraint governance_audit_events_actor_id_fkey to unexpected_actor_reference",
    );
    await assert.rejects(db.exec(migration), /constraint.*does not exist/);
    await db.exec("rollback");
    assert.equal(
      (
        await db.query(
          "select to_regclass('governance_private.account_history_identities') as relation",
        )
      ).rows[0].relation,
      null,
    );
    assert.equal(
      (
        await db.query(
          "select confrelid='auth.users'::regclass as original from pg_constraint where conname='workspace_memberships_user_id_fkey'",
        )
      ).rows[0].original,
      true,
    );
    await assert.rejects(
      db.query("delete from auth.users where id=$1", [MEMBER]),
      /foreign key/,
    );
  } finally {
    await db.close();
  }
});
