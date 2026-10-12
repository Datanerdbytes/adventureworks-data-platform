export function recoveryParameters(search, hash) {
  const params = new URLSearchParams(search);
  const fragment = new URLSearchParams(hash.replace(/^#/, ""));
  // The email template puts the one-time token in a fragment, avoiding HTTP logs.
  if (fragment.has("token_hash")) {
    params.set("token_hash", fragment.get("token_hash"));
    params.set("type", fragment.get("type") || "");
  }
  if (fragment.get("type") === "recovery") {
    for (const key of ["access_token", "refresh_token", "type"])
      if (fragment.has(key)) params.set(key, fragment.get(key));
  }
  return params;
}

export async function verifyRecoveryLink(client, params) {
  let result;
  if (params.has("access_token") || params.has("refresh_token")) {
    if (
      params.get("type") !== "recovery" ||
      !params.get("access_token") ||
      !params.get("refresh_token")
    )
      throw new Error("Use the link from your password-reset email.");
    // Only Supabase JS receives these tokens; they never enter Flask or Dash.
    result = await client.auth.setSession({
      access_token: params.get("access_token"),
      refresh_token: params.get("refresh_token"),
    });
  } else if (params.has("token_hash")) {
    if (params.get("type") !== "recovery")
      throw new Error("Use the link from your password-reset email.");
    result = await client.auth.verifyOtp({
      token_hash: params.get("token_hash"),
      type: "recovery",
    });
  } else if (params.has("code")) {
    result = await client.auth.exchangeCodeForSession(params.get("code"));
  } else {
    throw new Error("Request a new password-reset email to continue.");
  }
  if (result.error || !result.data?.session?.access_token)
    throw new Error(
      "This reset link is expired, invalid, or opened in another browser. Request a new reset email.",
    );
  return true;
}

export function recoveryEmailClient(createClient, config) {
  // Email links use Supabase's browser recovery flow so they can be opened on
  // another device. OAuth uses the separate, existing PKCE client.
  return createClient(config.url, config.publicKey, {
    auth: {
      flowType: "implicit",
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
      storageKey: "aw-recovery-email",
    },
  });
}

export async function updateRecoveredPassword(
  client,
  password,
  confirmation,
  verified,
) {
  if (!verified) throw new Error("Open a valid password-reset link first.");
  if (password.length < 12)
    throw new Error("Use at least 12 characters for your new password.");
  if (password !== confirmation) throw new Error("The passwords do not match.");
  const { error } = await client.auth.updateUser({ password });
  if (error) throw error;
}
