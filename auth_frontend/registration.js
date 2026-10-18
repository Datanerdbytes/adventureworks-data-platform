export function registrationCallback(mode, params) {
  return (
    mode === "callback" &&
    (params.get("registration") === "1" || params.get("type") === "signup")
  );
}

export async function exchangeCallbackCode(client, mode, params) {
  // Supabase's hosted verification endpoint confirms signup before redirecting.
  // Registration never needs a session, so its code must not require the
  // original browser's PKCE verifier. OAuth and recovery still require it.
  if (registrationCallback(mode, params)) return false;
  const { error } = await client.auth.exchangeCodeForSession(
    params.get("code"),
  );
  if (error) throw error;
  return true;
}

export function loginNotice(params) {
  if (params.get("password_reset") === "1")
    return "Password updated. Sign in with your new password.";
  if (params.get("registered") === "1")
    return "Sign in here after email verification and workspace approval. Verified accounts appear in the admin approval queue.";
  if (params.get("approval") === "revoked")
    return "Your workspace access has been revoked. Contact the workspace Owner or Admin.";
  if (params.get("approval") === "pending")
    return "Your account is awaiting workspace approval. Contact your Owner or Admin, then sign in again after approval.";
  if (params.get("approval") === "rejected")
    return "Your workspace access request was declined. Contact the workspace Owner or Admin.";
  if (["cancelled", "unavailable"].includes(params.get("approval")))
    return "Your account has no active workspace access. Contact the workspace Owner or Admin.";
  return "";
}

export async function submitRegistration(client, form, credentials) {
  const { error } = await client.auth.signUp(credentials);
  if (error) throw error;
  // Clear only after the provider accepts registration, keeping failures editable.
  form.reset();
  for (const name of ["email", "password"]) {
    const field = form.elements.namedItem(name);
    if (field) field.value = "";
  }
}
