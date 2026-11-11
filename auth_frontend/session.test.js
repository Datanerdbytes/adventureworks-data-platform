import test from "node:test";
import assert from "node:assert/strict";
import { sessionController, jsonRequest } from "./session.js";

test("synchronization is serialized and sends only access tokens", async () => {
  let running = 0,
    maximum = 0;
  const calls = [];
  const client = {
    auth: {
      getSession: async () => ({
        data: {
          session: { access_token: "access", refresh_token: "never-send" },
        },
      }),
      refreshSession: async () => {
        throw new Error("refresh must not run for a fresh session");
      },
    },
  };
  const controller = sessionController(
    client,
    async (url, options) => {
      running++;
      maximum = Math.max(maximum, running);
      await new Promise((resolve) => setImmediate(resolve));
      calls.push(options);
      running--;
      return { approved: true };
    },
    () => {},
  );
  await Promise.all([controller.sync(), controller.sync()]);
  assert.equal(maximum, 1);
  assert.equal(calls.length, 2);
  assert(!JSON.stringify(calls).includes("never-send"));
});
test("a near-expiry token is refreshed before synchronization", async () => {
  const calls = [];
  let refreshed = false;
  const client = {
    auth: {
      getSession: async () => ({
        data: {
          session: {
            access_token: "stale",
            expires_at: Math.floor((Date.now() + 10_000) / 1000),
          },
        },
      }),
      refreshSession: async () => {
        refreshed = true;
        return {
          data: { session: { access_token: "fresh" } },
          error: null,
        };
      },
    },
  };
  const controller = sessionController(
    client,
    async (url, options) => {
      calls.push(JSON.parse(options.body).access_token);
      return { approved: true };
    },
    () => {},
  );
  await controller.sync();
  assert(refreshed);
  assert.deepEqual(calls, ["fresh"]);
});

test("a failed refresh stops synchronization instead of sending a stale token", async () => {
  let posted = false;
  const client = {
    auth: {
      getSession: async () => ({
        data: {
          session: {
            access_token: "stale",
            expires_at: Math.floor((Date.now() - 10_000) / 1000),
          },
        },
      }),
      refreshSession: async () => ({
        data: { session: null },
        error: new Error("refresh rejected"),
      }),
    },
  };
  const controller = sessionController(
    client,
    async () => {
      posted = true;
      return { approved: true };
    },
    () => {},
  );
  await assert.rejects(controller.sync());
  assert(!posted);
});

test("sign-out clears app cookie and signs out even after synchronization fails", async () => {
  const calls = [];
  let exited = false;
  const client = {
    auth: {
      getSession: async () => ({
        data: { session: { access_token: "access" } },
      }),
      signOut: async () => {
        calls.push("sdk");
      },
    },
  };
  const controller = sessionController(
    client,
    async (url, options) => {
      calls.push(options.method);
      if (options.method === "POST") throw new Error("offline");
    },
    () => {
      exited = true;
    },
  );
  await assert.rejects(controller.sync());
  await controller.signOut();
  assert.deepEqual(calls, ["POST", "DELETE", "sdk"]);
  assert(exited);
});
test("rejected mutations are not replayed", async () => {
  let requests = 0;
  await assert.rejects(
    jsonRequest("/auth/workspace", { method: "POST" }, async () => {
      requests++;
      return {
        ok: false,
        status: 403,
        json: async () => ({ error: "Denied" }),
      };
    }),
    { status: 403 },
  );
  assert.equal(requests, 1);
});
test("missing browser session clears server cookie", async () => {
  let method;
  const client = {
    auth: { getSession: async () => ({ data: { session: null } }) },
  };
  const controller = sessionController(
    client,
    async (url, options) => {
      method = options.method;
    },
    () => {},
  );
  assert.equal(await controller.sync(), null);
  assert.equal(method, "DELETE");
});

test("throttled auth requests expose the server message without replay", async () => {
  let requests = 0;
  await assert.rejects(
    jsonRequest("/auth/session", { method: "POST" }, async () => {
      requests++;
      return {
        ok: false,
        status: 429,
        json: async () => ({
          error: "Too many requests. Please wait before trying again.",
        }),
      };
    }),
    {
      status: 429,
      message: "Too many requests. Please wait before trying again.",
    },
  );
  assert.equal(requests, 1);
});
