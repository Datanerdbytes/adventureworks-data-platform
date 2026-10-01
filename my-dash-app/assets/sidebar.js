(() => {
  let collapsed = false;
  const mobile = () => window.matchMedia("(max-width: 767px)").matches;
  function apply(value) {
    collapsed = value;
    document.body.classList.toggle("sidebar-collapsed", value);
    document
      .querySelector("#sidebar-toggle")
      ?.setAttribute("aria-expanded", String(!value));
    window.dispatchEvent(new Event("resize"));
  }
  function account(open, restore = false) {
    const menu = document.querySelector("#account-menu");
    const toggle = document.querySelector("#account-toggle");
    if (!menu || !toggle) return;
    menu.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) menu.querySelector("a, button")?.focus();
    else if (restore) toggle.focus();
  }
  function drawer(open, restore = true) {
    account(false);
    document.body.classList.toggle("drawer-open", open);
    document
      .querySelector("#mobile-menu")
      ?.setAttribute("aria-expanded", String(open));
    const aside = document.querySelector("#app-sidebar");
    if (aside) {
      if (open) {
        aside.setAttribute("role", "dialog");
        aside.setAttribute("aria-modal", "true");
        aside.setAttribute("aria-label", "Navigation");
      } else {
        aside.removeAttribute("role");
        aside.removeAttribute("aria-modal");
        aside.removeAttribute("aria-label");
      }
    }
    for (const selector of [".app-header", "#main-content"]) {
      const el = document.querySelector(selector);
      if (el) el.inert = open;
    }
    if (open) document.querySelector("#mobile-close")?.focus();
    else if (restore) document.querySelector("#mobile-menu")?.focus();
  }
  window.awSidebar = { apply };
  document.addEventListener("click", (e) => {
    if (e.target.closest("#account-toggle")) {
      account(document.querySelector("#account-menu")?.hidden);
    } else if (!e.target.closest("#account-menu")) {
      account(false);
    }
    if (e.target.closest("#account-menu a, #sidebar-toggle"))
      account(false, true);
    if (e.target.closest("#sidebar-toggle, #settings-collapse")) {
      apply(!collapsed);
      window.dash_clientside.set_props("sidebar-preference", {
        data: collapsed,
      });
    }
    if (e.target.closest("#mobile-menu")) drawer(true);
    if (e.target.closest("#mobile-close, #sidebar-backdrop")) drawer(false);
    if (e.target.closest("#app-sidebar a") && mobile()) drawer(false);
  });
  document.addEventListener("focusin", (e) => {
    if (!e.target.closest(".account-area")) account(false);
  });
  document.addEventListener("keydown", (e) => {
    if (
      e.key === "Escape" &&
      document.querySelector("#account-menu")?.hidden === false
    ) {
      e.preventDefault();
      account(false, true);
      return;
    }
    if (!document.body.classList.contains("drawer-open")) return;
    if (e.key === "Escape") {
      e.preventDefault();
      drawer(false);
    }
    if (e.key === "Tab") {
      const elements = [
        ...document.querySelectorAll("#app-sidebar button, #app-sidebar a"),
      ].filter((el) => el.getClientRects().length);
      const first = elements[0],
        last = elements[elements.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    }
  });
  window
    .matchMedia("(max-width: 767px)")
    .addEventListener("change", () => drawer(false, false));
})();
