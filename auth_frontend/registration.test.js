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
test("login explains verification without legacy workspace approval", () => {
  assert.match(
    loginNotice(new URLSearchParams("registered=1")),
    /verification complete/,
  );
  assert.equal(loginNotice(new URLSearchParams("approval=pending")), "");
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

test("signup clears both fields only after the provider accepts registration", async () => {
  const { submitRegistration } = await import("./registration.js");
  const email = { value: "signup@example.test" };
  const password = { value: "synthetic-registration-password" };
  let resets = 0;
  const form = {
    reset() {
      resets++;
    },
    elements: { namedItem: (name) => ({ email, password })[name] },
  };
  let finish;
  let received;
  const client = {
    auth: {
      signUp: (credentials) => {
        received = credentials;
        return new Promise((resolve) => {
          finish = resolve;
        });
      },
    },
  };
  const credentials = {
    email: email.value,
    password: password.value,
    options: {
      emailRedirectTo: "https://app.example/auth/callback?registration=1",
    },
  };
  const pending = submitRegistration(client, form, credentials);
  assert.equal(resets, 0);
  assert.equal(email.value, credentials.email);
  assert.equal(password.value, credentials.password);
  finish({ error: null });
  await pending;
  assert.equal(resets, 1);
  assert.equal(email.value, "");
  assert.equal(password.value, "");
  assert.deepEqual(received, credentials);
});

test("signup failure preserves the editable fields and propagates the error", async () => {
  const { submitRegistration } = await import("./registration.js");
  let resets = 0;
  const form = {
    reset() {
      resets++;
    },
  };
  for (const client of [
    {
      auth: {
        signUp: async () => ({ error: new Error("registration rejected") }),
      },
    },
    {
      auth: {
        signUp: async () => {
          throw new Error("network unavailable");
        },
      },
    },
  ]) {
    await assert.rejects(submitRegistration(client, form, {}));
    assert.equal(resets, 0);
  }
});
