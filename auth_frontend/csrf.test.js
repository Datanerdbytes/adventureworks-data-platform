import test from "node:test";
import assert from "node:assert/strict";
import { csrfFetch, monitorDashFetch } from "./csrf.js";

const token = "a".repeat(64);
const origin = "https://dashboard.example";
const issued = (value = token) => Response.json({ csrfToken: value });

test("issues current token before mutation and retains Request headers/body", async () => {
  const calls = [];
  const fetcher = async (input, init) => {
    calls.push([input, init]);
    return typeof input === "string" ? issued() : Response.json({ ok: true });
  };
  const wrapped = csrfFetch(fetcher, origin);
  const request = new Request(origin + "/_dash-update-component", {
    method: "POST",
    headers: new Headers({
      "Content-Type": "application/json",
      "X-Existing": "yes",
    }),
    body: JSON.stringify({ output: "read-or-write" }),
  });
  await wrapped(request);
  assert.equal(calls[0][1].headers["X-CSRF-Request"], "1");
  const sent = calls[1][0];
  assert.equal(sent.headers.get("X-CSRF-Token"), token);
  assert.equal(sent.headers.get("X-Existing"), "yes");
  assert.equal(sent.credentials, "same-origin");
  assert.equal(sent.redirect, "error");
  assert.equal((await sent.json()).output, "read-or-write");
});

test("init overrides Request method and headers without mutation", async () => {
  let sent;
  const wrapped = csrfFetch(async (input) => {
    if (typeof input === "string") return issued();
    sent = input;
    return new Response();
  }, origin);
  const request = new Request(origin + "/auth/password");
  const options = {
    method: "POST",
    headers: [["X-Existing", "kept"]],
    body: "{}",
  };
  await wrapped(request, options);
  assert.equal(sent.method, "POST");
  assert.equal(sent.headers.get("X-Existing"), "kept");
  assert.deepEqual(options.headers, [["X-Existing", "kept"]]);
});

test("external, unrelated same-origin and safe requests stay unchanged", async () => {
  const calls = [];
  const wrapped = csrfFetch(async (...args) => {
    calls.push(args);
    return new Response();
  }, origin);
  for (const url of [
    "https://project.supabase.co/auth/v1/token",
    "//foreign.example/auth/session",
    "/unrelated",
  ]) {
    const options = { method: "POST", headers: { "X-Existing": "yes" } };
    await wrapped(url, options);
    assert.equal(calls.at(-1)[0], url);
    assert.equal(calls.at(-1)[1], options);
    assert.equal(options.headers["X-CSRF-Token"], undefined);
  }
  await wrapped("/auth/session");
  assert.equal(calls.length, 4);
});

test("refresh and logout acquire new tokens; rejected writes are never replayed", async () => {
  let current = "a".repeat(64);
  const sent = [];
  const wrapped = csrfFetch(async (input) => {
    if (typeof input === "string") return issued(current);
    sent.push(input.headers.get("X-CSRF-Token"));
    return new Response("denied", { status: 403 });
  }, origin);
  assert.equal(
    (await wrapped("/auth/session", { method: "POST" })).status,
    403,
  );
  current = "b".repeat(64);
  await wrapped("/auth/session", { method: "DELETE" });
  assert.deepEqual(sent, ["a".repeat(64), "b".repeat(64)]);
});

test("issuance failure, malformed token and cancellation prevent mutation", async () => {
  for (const response of [
    new Response("failed", { status: 403 }),
    issued("bad"),
  ]) {
    let count = 0;
    const wrapped = csrfFetch(async () => {
      count++;
      return response;
    }, origin);
    await assert.rejects(wrapped("/auth/password", { method: "POST" }));
    assert.equal(count, 1);
  }
  const abort = new AbortController();
  abort.abort();
  const wrapped = csrfFetch(async (input, options) => {
    options.signal.throwIfAborted();
  }, origin);
  await assert.rejects(
    wrapped("/auth/session", { method: "DELETE", signal: abort.signal }),
  );
});

test("concurrent initial mutations serialize security issuance and writes", async () => {
  const sequence = [];
  const wrapped = csrfFetch(async (input) => {
    sequence.push(typeof input === "string" ? "issue" : "write");
    await Promise.resolve();
    return typeof input === "string" ? issued() : new Response();
  }, origin);
  await Promise.all([
    wrapped("/auth/session", { method: "POST" }),
    wrapped("/_dash-update-component", { method: "POST" }),
  ]);
  assert.deepEqual(sequence, ["issue", "write", "issue", "write"]);
});

test("foreign Request body is not consumed before passthrough", async () => {
  const request = new Request("https://project.supabase.co/auth/v1/token", {
    method: "POST",
    body: "unchanged-body",
    headers: { "Content-Type": "application/json" },
  });
  const wrapped = csrfFetch(async (input, init) => {
    assert.equal(input, request);
    assert.equal(init, undefined);
    assert.equal(input.bodyUsed, false);
    assert.equal(await input.text(), "unchanged-body");
    assert.equal(input.headers.get("X-CSRF-Token"), null);
    return new Response();
  }, origin);
  await wrapped(request);
});

test("slow Dash responses do not serialize callback execution", async () => {
  let release;
  const first = new Promise((resolve) => {
    release = resolve;
  });
  let writes = 0;
  const wrapped = csrfFetch(async (input) => {
    if (typeof input === "string") return issued();
    writes++;
    return writes === 1 ? first : new Response();
  }, origin);
  const pending = wrapped("/_dash-update-component", { method: "POST" });
  await wrapped("/_dash-update-component", { method: "POST" });
  assert.equal(writes, 2);
  release(new Response());
  await pending;
});

test("Dash token issuance failures block display without replay", async () => {
  const failures = [];
  let calls = 0;
  const secured = csrfFetch(async () => {
    calls++;
    return new Response("busy", { status: 429 });
  }, origin);
  const monitored = monitorDashFetch(secured, origin, (error) =>
    failures.push(error.message),
  );
  await assert.rejects(
    monitored("/_dash-update-component", { method: "POST" }),
  );
  assert.equal(calls, 1);
  assert.equal(failures.length, 1);
  assert.match(failures[0], /Security session unavailable/);
});

test("Dash HTTP denials block display, foreign failures do not", async () => {
  const failures = [];
  const monitored = monitorDashFetch(
    async () => new Response("denied", { status: 403 }),
    origin,
    (error) => failures.push(error),
  );
  await monitored("/_dash-update-component", { method: "POST" });
  await monitored("https://project.supabase.co/_dash-update-component", {
    method: "POST",
  });
  assert.equal(failures.length, 1);
});
