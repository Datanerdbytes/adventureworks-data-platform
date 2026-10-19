// Recovery sessions are private to this page. Only the one-time PKCE verifier
// crosses pages; access/refresh tokens never enter the normal client's storage.
export function recoveryParameters(search) {
  return new URLSearchParams(search);
}

export function recoveryEmailClient(
  createClient,
  config,
  storage = localStorage,
  id = crypto.randomUUID(),
) {
  const normalKey = `sb-${new URL(config.url).hostname.split(".")[0]}-auth-token`;
  const recoveryKey = `${normalKey}-recovery-${id}`;
  const memory = new Map();
  const verifierPrefix = `${normalKey}-account-recovery`;
  const sharedVerifier = (key) => {
    if (!key.startsWith(recoveryKey)) return null;
    const suffix = key.slice(recoveryKey.length);
    return /^-(?:flow-[a-zA-Z0-9_-]{8,64}-|flows-)?code-verifier$/.test(suffix)
      ? verifierPrefix + suffix
      : null;
  };
  return createClient(config.url, config.publicKey, {
    auth: {
      flowType: "pkce",
      detectSessionInUrl: false,
      persistSession: true,
      autoRefreshToken: false,
      storageKey: recoveryKey,
      storage: {
        getItem(key) {
          const shared = sharedVerifier(key);
          return shared ? storage.getItem(shared) : (memory.get(key) ?? null);
        },
        setItem(key, value) {
          const shared = sharedVerifier(key);
          if (shared) storage.setItem(shared, value);
          else memory.set(key, value);
        },
        removeItem(key) {
          const shared = sharedVerifier(key);
          if (shared) storage.removeItem(shared);
          memory.delete(key);
        },
      },
    },
  });
}

export async function verifyRecoveryLink(client, params) {
  if (
    !params.get("code") ||
    params.has("access_token") ||
    params.has("refresh_token") ||
    params.has("token_hash")
  )
    throw new Error(
      "Request a new password-reset email and open the link in this browser.",
    );
  const flowId = params.get("sb_flow_id");
  const result = await client.auth.exchangeCodeForSession(
    params.get("code"),
    flowId ? { flowId } : undefined,
  );
  const id = result.data?.session?.user?.id;
  if (
    result.error ||
    result.data?.redirectType !== "recovery" ||
    !result.data?.session?.access_token ||
    !id
  )
    throw new Error(
      "This reset link is expired or invalid. Request a new reset email in this browser.",
    );
  return id;
}

export async function updateRecoveredPassword(
  client,
  password,
  confirmation,
  identity,
) {
  if (typeof identity !== "string" || !identity)
    throw new Error("Open a valid password-reset link first.");
  if (password.length < 12)
    throw new Error("Use at least 12 characters for your new password.");
  if (password !== confirmation) throw new Error("The passwords do not match.");
  const current = await client.auth.getSession();
  if (current.error || current.data?.session?.user?.id !== identity)
    throw new Error(
      "Your recovery session changed or ended. Request a new reset link.",
    );
  const { error } = await client.auth.updateUser({ password });
  if (error) throw error;
}
