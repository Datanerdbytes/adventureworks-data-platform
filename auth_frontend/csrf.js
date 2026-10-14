// Protect only application mutations, never requests to Supabase or other origins.
const protectedPaths = new Set([
  "/auth/session",
  "/auth/workspace",
  "/_dash-update-component",
]);
const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function csrfFetch(fetcher, baseUrl) {
  const base = new URL(baseUrl);
  let queue = Promise.resolve();
  return (input, options) => {
    const target = new URL(input instanceof Request ? input.url : input, base);
    const method =
      options?.method || (input instanceof Request ? input.method : "GET");
    if (
      target.origin !== base.origin ||
      !protectedPaths.has(target.pathname) ||
      !unsafeMethods.has(method.toUpperCase())
    ) {
      return fetcher(input, options);
    }
    const request = new Request(
      input instanceof Request ? input : target,
      options,
    );
    // Keep issuance + mutation paired within this tab. Cross-tab cookie changes
    // may reject a pending mutation; never retry it automatically.
    const send = async () => {
      const issued = await fetcher(new URL("/auth/csrf", base).href, {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        headers: { "X-CSRF-Request": "1" },
        signal: request.signal,
      });
      if (!issued.ok)
        throw new Error("Security session unavailable. Reload to retry.");
      const { csrfToken } = await issued.json();
      if (typeof csrfToken !== "string" || !/^[a-f0-9]{64}$/.test(csrfToken)) {
        throw new Error("Security session unavailable. Reload to retry.");
      }
      const headers = new Headers(request.headers);
      headers.set("X-CSRF-Token", csrfToken);
      return {
        response: fetcher(
          new Request(request, {
            headers,
            credentials: "same-origin",
            redirect: "error",
          }),
        ),
      };
    };
    const dispatched = queue.catch(() => {}).then(send);
    // Release after dispatch: slow data callbacks must remain concurrent.
    queue = dispatched.then(
      () => {},
      () => {},
    );
    return dispatched.then(({ response }) => response);
  };
}

export function monitorDashFetch(fetcher, baseUrl, onFailure) {
  const base = new URL(baseUrl);
  return async (input, options) => {
    const target = new URL(input instanceof Request ? input.url : input, base);
    const dash =
      target.origin === base.origin && target.pathname.startsWith("/_dash");
    try {
      const response = await fetcher(input, options);
      if (dash && [401, 403, 503].includes(response.status)) {
        onFailure(
          new Error(
            "Your access changed or the service is unavailable. Reload to sign in and retry.",
          ),
        );
      }
      return response;
    } catch (error) {
      if (dash) onFailure(error);
      throw error;
    }
  };
}
