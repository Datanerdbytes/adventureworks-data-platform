// Serialize cookie synchronization. Never retry a user's rejected mutation.
export function sessionController(client, request, onSignedOut) {
  let queue = Promise.resolve();
  let stopped = false;
  const sync = (next = "/dashboard") => {
    queue = queue
      .catch(() => {})
      .then(async () => {
        const { data, error } = await client.auth.getSession();
        if (error) throw error;
        if (!data.session || stopped) {
          await request("/auth/session", { method: "DELETE" });
          return null;
        }
        return request("/auth/session", {
          method: "POST",
          body: JSON.stringify({
            access_token: data.session.access_token,
            next,
          }),
        });
      });
    return queue;
  };
  const signOut = async () => {
    stopped = true;
    try {
      // Clear the application cookie even if remote sign-out fails.
      await queue.catch(() => {});
      await request("/auth/session", { method: "DELETE" });
    } finally {
      await client.auth.signOut({ scope: "local" });
      onSignedOut();
    }
  };
  return { sync, signOut };
}

export async function jsonRequest(url, options = {}, fetcher = fetch) {
  const response = await fetcher(url, {
    credentials: "same-origin",
    cache: "no-store",
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(
      body.error || "The request could not be completed.",
    );
    error.status = response.status;
    throw error;
  }
  return body;
}
