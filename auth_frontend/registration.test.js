import test from "node:test";
import assert from "node:assert/strict";
import {
  registrationCallback,
  loginNotice,
  exchangeCallbackCode,
} from "./registration.js";

test("email confirmation is a registration step, not automatic sign-in", () => {
  assert(
    registrationCallback(
      "callback",
      new URLSearchParams("registration=1&code=confirmation"),
    ),
  );
  assert(
    registrationCallback(
      "callback",
      new URLSearchParams("type=signup&token_hash=confirmation"),
    ),
  );
  assert(!registrationCallback("callback", new URLSearchParams("code=oauth")));
  assert(
    !registrationCallback("recovery", new URLSearchParams("type=recovery")),
  );
});
test("login explains verification and pending approval without exposing identities", () => {
  assert.match(
    loginNotice(new URLSearchParams("registered=1")),
    /email verification and workspace approval/,
  );
  assert.match(
    loginNotice(new URLSearchParams("approval=pending")),
    /awaiting workspace approval/,
  );
  assert.equal(loginNotice(new URLSearchParams()), "");
});

test("signup redirect needs no PKCE storage and creates no session", async () => {
  const client = {
    auth: {
      exchangeCodeForSession() {
        throw new Error("missing verifier");
      },
    },
  };
  assert.equal(
    await exchangeCallbackCode(
      client,
      "callback",
      new URLSearchParams("registration=1&code=signup"),
    ),
    false,
  );
});

test("OAuth and recovery still exchange codes and propagate failures", async () => {
  const codes = [];
  const client = {
    auth: {
      async exchangeCodeForSession(code) {
        codes.push(code);
        return { error: null };
      },
    },
  };
  assert.equal(
    await exchangeCallbackCode(
      client,
      "callback",
      new URLSearchParams("code=oauth"),
    ),
    true,
  );
  assert.equal(
    await exchangeCallbackCode(
      client,
      "recovery",
      new URLSearchParams("code=recovery"),
    ),
    true,
  );
  assert.deepEqual(codes, ["oauth", "recovery"]);
  client.auth.exchangeCodeForSession = async () => ({
    error: new Error("invalid code"),
  });
  await assert.rejects(
    exchangeCallbackCode(client, "callback", new URLSearchParams("code=bad")),
    /invalid code/,
  );
});

test("rejected requests do not masquerade as pending approval", () => {
  assert.match(
    loginNotice(new URLSearchParams("approval=rejected")),
    /declined/,
  );
  assert.match(
    loginNotice(new URLSearchParams("approval=unavailable")),
    /no active workspace access/,
  );
});

test("revoked access is distinct from pending approval", () => {
  const message = loginNotice(new URLSearchParams("approval=revoked"));
  assert.match(message, /access has been revoked/);
  assert.match(message, /Owner or Admin/);
  assert.doesNotMatch(message, /awaiting/);
});
