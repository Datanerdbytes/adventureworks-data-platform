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
    return "Email verification complete. Sign in to access analytics.";
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
