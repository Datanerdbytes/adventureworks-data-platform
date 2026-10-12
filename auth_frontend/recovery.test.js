import test from "node:test";
import assert from "node:assert/strict";
import {
  recoveryParameters,
  verifyRecoveryLink,
  updateRecoveredPassword,
  recoveryEmailClient,
} from "./recovery.js";

const session = { access_token: "synthetic", user: { id: "fixture" } };

test("default recovery email works across browsers without a PKCE verifier", async () => {
  const params = recoveryParameters(
    "?step=update",
    "#access_token=synthetic&refresh_token=synthetic-refresh&type=recovery",
  );
  const calls = [];
  const client = {
    auth: {
      async setSession(tokens) {
        calls.push(tokens);
        return { data: { session }, error: null };
      },
    },
  };
  assert.equal(await verifyRecoveryLink(client, params), true);
  assert.deepEqual(calls, [
    { access_token: "synthetic", refresh_token: "synthetic-refresh" },
  ]);
  await assert.rejects(
    verifyRecoveryLink(
      client,
      new URLSearchParams("access_token=synthetic&type=recovery"),
    ),
    /password-reset email/,
  );
  assert.equal(
    recoveryParameters(
      "?step=update",
      "#access_token=synthetic&type=signup",
    ).has("access_token"),
    false,
  );
});

test("recovery email sender is isolated and never stores a browser session", () => {
  let options;
  const client = {};
  assert.equal(
    recoveryEmailClient(
      (url, key, settings) => {
        options = settings.auth;
        return client;
      },
      { url: "https://fixture.supabase.co", publicKey: "public" },
    ),
    client,
  );
  assert.equal(options.flowType, "implicit");
  assert.equal(options.persistSession, false);
  assert.equal(options.autoRefreshToken, false);
  assert.equal(options.detectSessionInUrl, false);
});

test("fragment recovery works without PKCE browser storage", async () => {
  const params = recoveryParameters(
    "?step=update",
    "#token_hash=one-time&type=recovery",
  );
  const calls = [];
  const client = {
    auth: {
      async verifyOtp(payload) {
        calls.push(payload);
        return { data: { session }, error: null };
      },
      exchangeCodeForSession() {
        throw new Error("No PKCE verifier");
      },
    },
  };
  assert.equal(await verifyRecoveryLink(client, params), true);
  assert.deepEqual(calls, [{ token_hash: "one-time", type: "recovery" }]);
});

test("legacy recovery links still require a successful PKCE exchange", async () => {
  const client = {
    auth: {
      async exchangeCodeForSession(code) {
        assert.equal(code, "recovery-code");
        return { data: { session }, error: null };
      },
    },
  };
  assert.equal(
    await verifyRecoveryLink(client, new URLSearchParams("code=recovery-code")),
    true,
  );
});

test("missing, expired, and non-recovery links cannot enable password update", async () => {
  const client = {
    auth: {
      async verifyOtp() {
        return { error: new Error("expired") };
      },
    },
  };
  await assert.rejects(
    verifyRecoveryLink(client, new URLSearchParams("step=update")),
    /new password-reset email/,
  );
  await assert.rejects(
    verifyRecoveryLink(client, new URLSearchParams("token_hash=x&type=signup")),
    /password-reset email/,
  );
  await assert.rejects(
    verifyRecoveryLink(
      client,
      new URLSearchParams("token_hash=x&type=recovery"),
    ),
    /expired, invalid/,
  );
});

test("passwords require verification, minimum length, and matching confirmation", async () => {
  const writes = [];
  const client = {
    auth: {
      async updateUser(payload) {
        writes.push(payload);
        return { error: null };
      },
    },
  };
  await assert.rejects(
    updateRecoveredPassword(
      client,
      "fixture-password",
      "fixture-password",
      false,
    ),
    /valid password-reset link/,
  );
  await assert.rejects(
    updateRecoveredPassword(client, "short", "short", true),
    /12 characters/,
  );
  await assert.rejects(
    updateRecoveredPassword(client, "fixture-password", "different", true),
    /do not match/,
  );
  assert.equal(writes.length, 0);
  await updateRecoveredPassword(
    client,
    "fixture-password",
    "fixture-password",
    true,
  );
  assert.deepEqual(writes, [{ password: "fixture-password" }]);
});

test("Supabase update errors remain visible", async () => {
  const client = {
    auth: {
      async updateUser() {
        return { error: new Error("Password policy rejected") };
      },
    },
  };
  await assert.rejects(
    updateRecoveredPassword(
      client,
      "fixture-password",
      "fixture-password",
      true,
    ),
    /policy rejected/,
  );
});
