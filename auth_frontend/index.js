import { csrfFetch, monitorDashFetch } from "./csrf.js";
import { createClient } from "@supabase/supabase-js";
import { jsonRequest, sessionController } from "./session.js";
import {
  recoveryParameters,
  verifyRecoveryLink,
  updateRecoveredPassword,
  recoveryEmailClient,
} from "./recovery.js";
import {
  registrationCallback,
  loginNotice,
  exchangeCallbackCode,
  submitRegistration,
} from "./registration.js";

// Install before cookie synchronization and before Dash's renderer starts.
window.fetch = csrfFetch(window.fetch.bind(window), location.href);

let startRenderer;
let ready = false;
window.awAuthStart = (start) => {
  startRenderer = start;
  if (ready) start();
};
const mode = document.documentElement.dataset.authMode;
const isDashboard = !mode;
let client, controller;
const status = (message, error = false) => {
  const node = document.getElementById("auth-status");
  if (node) {
    node.textContent = message;
    node.classList.toggle("auth-error", error);
  }
};
const failure = (error) => {
  status(
    error.message || "Authentication is unavailable. Reload to retry.",
    true,
  );
  if (isDashboard) {
    document.body.classList.add("auth-blocked");
    document.getElementById("auth-startup")?.removeAttribute("hidden");
  }
};
const destination = () => document.documentElement.dataset.next || "/dashboard";
const disable = (form, value) =>
  form.querySelectorAll("button").forEach((b) => {
    b.disabled = value;
  });

document.addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-password-toggle]");
  if (!toggle) return;
  const field = document.getElementById(toggle.dataset.passwordToggle);
  if (!field) return;
  const show = field.type === "password";
  field.type = show ? "text" : "password";
  toggle.setAttribute("aria-pressed", String(show));
  toggle.textContent = show ? "Hide password" : "Show password";
});

async function initialize() {
  const params =
    mode === "recovery"
      ? recoveryParameters(location.search, location.hash)
      : new URLSearchParams(location.search);
  let recoveryVerified = false;
  const confirmingRegistration = registrationCallback(mode, params);
  let signedOutDestination = confirmingRegistration
    ? "/login?registered=1"
    : "/login";
  const config = await jsonRequest("/auth/config");
  client =
    mode === "recovery"
      ? recoveryEmailClient(createClient, config)
      : createClient(config.url, config.publicKey, {
          auth: {
            flowType: "pkce",
            detectSessionInUrl: false,
            persistSession: true,
            autoRefreshToken: true,
          },
        });
  controller = sessionController(client, jsonRequest, () =>
    location.assign(signedOutDestination),
  );
  if (params.has("error"))
    throw new Error(
      "Sign-in could not be completed. New users must sign up with email first and verify their email. Existing users can retry or use email/password.",
    );
  if (mode === "recovery" && params.get("step") === "update") {
    history.replaceState(null, "", "/auth/recovery?step=update");
    recoveryVerified = await verifyRecoveryLink(client, params);
    await jsonRequest("/auth/session", { method: "DELETE" });
    status("Choose a new password with at least 12 characters.");
  } else if (params.has("code")) {
    const exchanged = await exchangeCallbackCode(client, mode, params);
    history.replaceState(null, "", location.pathname);
    if (!exchanged) {
      // No session was created: do not sign out an unrelated existing account.
      location.replace(signedOutDestination);
      return;
    }
  } else if (params.has("token_hash")) {
    const type = params.get("type");
    if (!["signup", "email"].includes(type))
      throw new Error("Unsupported confirmation link.");
    const { error } = await client.auth.verifyOtp({
      token_hash: params.get("token_hash"),
      type,
    });
    history.replaceState(null, "", location.pathname);
    if (error) throw error;
  }
  client.auth.onAuthStateChange((event, session) => {
    if (mode === "recovery") {
      if (
        recoveryVerified &&
        (event === "SIGNED_OUT" || session?.user?.id !== recoveryVerified)
      ) {
        recoveryVerified = false;
        document
          .getElementById("auth-form")
          ?.querySelector('button[type="submit"]')
          ?.setAttribute("disabled", "");
        failure(
          new Error(
            "Your recovery session changed or ended. Request a new reset link.",
          ),
        );
      }
      return;
    }
    // SDK auth callbacks must return immediately; session reads happen outside the callback.
    if (event === "SIGNED_OUT") {
      setTimeout(
        () =>
          controller
            .sync()
            .then(() => {
              if (isDashboard) location.assign("/login");
            })
            .catch(failure),
        0,
      );
    } else if (
      mode !== "signup" &&
      mode !== "recovery" &&
      !confirmingRegistration &&
      ["TOKEN_REFRESHED", "SIGNED_IN", "USER_UPDATED"].includes(event)
    ) {
      setTimeout(
        () =>
          controller
            .sync()
            .then((result) => {
              if (isDashboard && !result) location.assign("/login");
            })
            .catch(failure),
        0,
      );
    }
  });
  for (const provider of config.providers) {
    const button = document.querySelector(`[data-provider="${provider}"]`);
    if (button) {
      button.closest(".auth-providers").hidden = false;
      button.hidden = false;
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          const { error } = await client.auth.signInWithOAuth({
            provider,
            options: {
              redirectTo:
                location.origin +
                "/auth/callback?next=" +
                encodeURIComponent(destination()),
            },
          });
          if (error) throw error;
        } catch (error) {
          failure(error);
          button.disabled = false;
        }
      });
    }
  }
  document.addEventListener("click", async (event) => {
    if (event.target.closest("#auth-sign-out")) {
      try {
        await controller.signOut();
      } catch (error) {
        failure(error);
      }
    }
    if (event.target.closest("#auth-retry")) location.reload();
  });
  document
    .getElementById("auth-form")
    ?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.target,
        values = new FormData(form);
      disable(form, true);
      status("Working…");
      try {
        const email = String(values.get("email") || "").trim();
        const password = String(values.get("password") || "");
        if (mode === "signup") {
          await submitRegistration(client, form, {
            email,
            password,
            options: {
              emailRedirectTo:
                location.origin + "/auth/callback?registration=1",
            },
          });
          status(
            "Check your email to confirm your account, then return to sign in.",
          );
        } else if (mode === "recovery" && params.get("step") === "update") {
          await updateRecoveredPassword(
            client,
            password,
            String(values.get("password_confirmation") || ""),
            recoveryVerified,
          );
          recoveryVerified = false;
          form.reset();
          await jsonRequest("/auth/session", { method: "DELETE" });
          const revoked = await client.auth.signOut({ scope: "global" });
          if (revoked.error) throw revoked.error;
          const normal = createClient(config.url, config.publicKey, {
            auth: { flowType: "pkce", detectSessionInUrl: false },
          });
          const cleared = await normal.auth.signOut({ scope: "local" });
          if (cleared.error) throw cleared.error;
          location.assign("/login?password_reset=1");
        } else if (mode === "recovery") {
          const sender = client;
          const { error } = await sender.auth.resetPasswordForEmail(email, {
            redirectTo: location.origin + "/auth/recovery?step=update",
          });
          if (error) throw error;
          status(
            "If the account exists, a recovery email will arrive shortly. Open the latest link in this browser.",
          );
        } else {
          let result;
          if (config.passwordLockoutEnabled) {
            const tokens = await jsonRequest("/auth/password", {
              method: "POST",
              body: JSON.stringify({ email, password }),
            });
            result = await client.auth.setSession(tokens);
          } else
            result = await client.auth.signInWithPassword({ email, password });
          const { error } = result;
          if (error) throw error;
          const synced = await controller.sync(destination());
          if (!synced) throw new Error("Sign-in did not establish a session.");
          location.assign(synced.next);
        }
      } catch (error) {
        failure(error);
      } finally {
        disable(form, false);
        if (
          mode === "recovery" &&
          params.get("step") === "update" &&
          !recoveryVerified
        )
          form
            .querySelector('button[type="submit"]')
            ?.setAttribute("disabled", "");
      }
    });
  const initializedForm = document.getElementById("auth-form");
  if (initializedForm) disable(initializedForm, false);
  if (mode === "recovery" && !recoveryVerified)
    status("Enter your email to receive a password-reset link.");
  if (mode === "callback") {
    if (confirmingRegistration) {
      // Verification completes registration, never an automatic dashboard login.
      await controller.signOut();
      return;
    }
    const result = await controller.sync(destination());
    if (!result)
      throw new Error(
        "No session was established. Return to sign-in and retry.",
      );
    location.replace(result.next);
  } else if (isDashboard) {
    const result = await controller.sync(location.pathname);
    if (!result) return location.replace("/login");
    await jsonRequest("/auth/status");
    // HTTP failures stop the display but never replay data mutations.
    window.fetch = monitorDashFetch(
      window.fetch.bind(window),
      location.href,
      failure,
    );
    ready = true;
    document.body.classList.remove("auth-blocked");
    document.getElementById("auth-startup")?.setAttribute("hidden", "");
    startRenderer?.();
  } else if (mode === "login") status(loginNotice(params));
}

if (document.readyState === "loading")
  document.addEventListener(
    "DOMContentLoaded",
    () => initialize().catch(failure),
    { once: true },
  );
else initialize().catch(failure);
