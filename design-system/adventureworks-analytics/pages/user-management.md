# User Management

Follow MASTER.md and the existing Dash/DBC console. This replaces the retired
workspace-admin screens for the owner/admin account model.

- Keep the existing dashboard navigation and shared AdventureWorks identity.
- `/admin/users` is administrator-only; server checks also protect callbacks/API writes.
- Place result notices above the directory. Success notices last five seconds with
  a new timer per result; errors remain visible. Scroll new feedback into view.
- Fetch at most 25 provider accounts per page; display ten grid rows per page.
  Explicitly explain that column filters cover the current provider page.
- Single account selection enables relevant actions. Explain owner/self protection,
  verification requirements, and demotion before suspension beside the controls.
- Confirm access changes in a labeled DBC modal. Owner-only deletion requires a
  suspended non-admin, a typed matching email, and explicit irreversible wording.
- Use 44px controls, keyboard focus, responsive wrapped actions and announced notices.
- Reuse semantic light/dark tokens and the existing scoped DBC modal structure.
- Layout functions use empty grids; all provider reads happen in authorized callbacks.
