import test from "node:test";
import assert from "node:assert/strict";
import {
  recoveryParameters,
  recoveryEmailClient,
  verifyRecoveryLink,
  updateRecoveredPassword,
} from "./recovery.js";

const session = {
  access_token: "synthetic",
  user: { id: "recovering-account" },
};
test("isolated PKCE client shares only verifier and never account tokens", () => {
  const saved = new Map();
  const storage = {
    getItem: (k) => saved.get(k) ?? null,
    setItem: (k, v) => saved.set(k, v),
    removeItem: (k) => saved.delete(k),
  };
  let auth;
  recoveryEmailClient(
    (url, key, options) => {
      auth = options.auth;
      return {};
    },
    { url: "https://fixture.supabase.co", publicKey: "public" },
    storage,
    "unique-tab",
  );
  assert.equal(auth.flowType, "pkce");
  assert.equal(auth.autoRefreshToken, false);
  const key = auth.storageKey;
  auth.storage.setItem(`${key}-code-verifier`, "one-time/recovery");
  auth.storage.setItem(key, "private-recovery-session");
  assert.deepEqual(
    [...saved.entries()],
    [
      [
        "sb-fixture-auth-token-account-recovery-code-verifier",
        "one-time/recovery",
      ],
    ],
  );
  assert.equal(auth.storage.getItem(key), "private-recovery-session");
  auth.storage.removeItem(`${key}-code-verifier`);
  assert.equal(saved.size, 0);
  let second;
  recoveryEmailClient(
    (u, k, o) => {
      second = o.auth;
      return {};
    },
    { url: "https://fixture.supabase.co", publicKey: "public" },
    storage,
    "second-tab",
  );
  assert.notEqual(second.storageKey, key);
  assert.equal(second.storage.getItem(key), null);
});
test("only an exchanged recovery code establishes a bound identity", async () => {
  const client = {
    auth: {
      exchangeCodeForSession: async (code) => {
        assert.equal(code, "one-time");
        return { data: { session, redirectType: "recovery" }, error: null };
      },
    },
  };
  assert.equal(
    await verifyRecoveryLink(client, recoveryParameters("?code=one-time")),
    "recovering-account",
  );
  for (const query of [
    "",
    "?token_hash=legacy&type=recovery",
    "?access_token=other&refresh_token=other&type=recovery",
  ]) {
    await assert.rejects(
      verifyRecoveryLink(client, recoveryParameters(query)),
      /new password-reset email/,
    );
  }
  client.auth.exchangeCodeForSession = async () => ({
    data: { session, redirectType: null },
    error: null,
  });
  await assert.rejects(
    verifyRecoveryLink(client, recoveryParameters("?code=oauth")),
    /expired or invalid/,
  );
});
test("normal cached sessions and fragments cannot establish recovery", async () => {
  const params = recoveryParameters(
    "?step=update",
    "#access_token=foreign&refresh_token=foreign&type=recovery",
  );
  await assert.rejects(
    verifyRecoveryLink({}, params),
    /new password-reset email/,
  );
  await assert.rejects(
    updateRecoveredPassword(
      {},
      "long-enough-password",
      "long-enough-password",
      true,
    ),
    /valid password-reset/,
  );
});
test("password update validates current identity and confirmation before mutation", async () => {
  const calls = [];
  const client = {
    auth: {
      getSession: async () => ({ data: { session } }),
      updateUser: async (body) => {
        calls.push(body);
        return { error: null };
      },
    },
  };
  await assert.rejects(
    updateRecoveredPassword(client, "short", "short", "recovering-account"),
    /12 characters/,
  );
  await assert.rejects(
    updateRecoveredPassword(
      client,
      "long-enough-password",
      "mismatch",
      "recovering-account",
    ),
    /do not match/,
  );
  await assert.rejects(
    updateRecoveredPassword(
      client,
      "long-enough-password",
      "long-enough-password",
      "another-account",
    ),
    /changed or ended/,
  );
  assert.equal(calls.length, 0);
  await updateRecoveredPassword(
    client,
    "long-enough-password",
    "long-enough-password",
    "recovering-account",
  );
  assert.deepEqual(calls, [{ password: "long-enough-password" }]); // pragma: allowlist secret (synthetic test data or non-secret feature flag)
  client.auth.getSession = async () => ({ data: { session: null } });
  await assert.rejects(
    updateRecoveredPassword(
      client,
      "long-enough-password",
      "long-enough-password",
      "recovering-account",
    ),
    /changed or ended/,
  );
});

for (const appendFlowIds of [false, true])
  test(`installed SDK recovery across isolated pages, flow IDs: ${appendFlowIds}`, async () => {
    const { createClient } = await import("@supabase/supabase-js");
    const saved = new Map();
    const storage = {
      getItem: (k) => saved.get(k) ?? null,
      setItem: (k, v) => saved.set(k, v),
      removeItem: (k) => saved.delete(k),
    };
    let redirect;
    let exchanged;
    const payload = Buffer.from(
      JSON.stringify({
        exp: Math.floor(Date.now() / 1000) + 3600,
        sub: "11111111-1111-4111-8111-111111111111",
        aud: "authenticated",
      }),
    ).toString("base64url");
    const access = `eyJhbGciOiJIUzI1NiJ9.${payload}.fixture`;
    const factory = (url, key, options) =>
      createClient(url, key, {
        ...options,
        auth: {
          ...options.auth,
          experimental: { appendPkceFlowIdToRedirects: appendFlowIds },
        },
        global: {
          fetch: async (input, init) => {
            const target = new URL(input);
            if (target.pathname.endsWith("/recover")) {
              redirect = new URL(target.searchParams.get("redirect_to"));
              return new Response("{}", { status: 200 });
            }
            if (target.pathname.endsWith("/token")) {
              exchanged = JSON.parse(init.body);
              return new Response(
                JSON.stringify({
                  access_token: access,
                  refresh_token: "synthetic-refresh",
                  expires_in: 3600,
                  token_type: "bearer",
                  user: {
                    id: "11111111-1111-4111-8111-111111111111",
                    email: "fixture@example.test",
                  },
                }),
                { status: 200 },
              );
            }
            throw new Error("Unexpected provider call");
          },
        },
      });
    const config = {
      url: "https://fixture.supabase.co",
      publicKey: "synthetic-public",
    };
    const sender = recoveryEmailClient(
      factory,
      config,
      storage,
      "request-page",
    );
    const requested = await sender.auth.resetPasswordForEmail(
      "fixture@example.test",
      { redirectTo: "https://app.example/auth/recovery?step=update" },
    );
    assert.equal(requested.error, null);
    assert.equal(
      Boolean(redirect.searchParams.get("sb_flow_id")),
      appendFlowIds,
    );
    assert([...saved.keys()].every((k) => k.endsWith("code-verifier")));
    redirect.searchParams.set("code", "recovery-code");
    const receiver = recoveryEmailClient(
      factory,
      config,
      storage,
      "update-page",
    );
    const id = await verifyRecoveryLink(receiver, redirect.searchParams);
    assert.equal(id, "11111111-1111-4111-8111-111111111111");
    assert.equal(exchanged.auth_code, "recovery-code");
    assert.equal(typeof exchanged.code_verifier, "string");
    assert(exchanged.code_verifier.length > 20);
    assert(
      [...saved.values()].every(
        (v) => !v.includes("synthetic-refresh") && !v.includes(access),
      ),
    );
    sender.auth.stopAutoRefresh();
    receiver.auth.stopAutoRefresh();
  });
