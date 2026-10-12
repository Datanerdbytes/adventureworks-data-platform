# Workspace Administration

Follow MASTER.md and the existing Dash/DBC console styling.

- Two columns of white bordered panels on wide desktops, one column below 1100px.
- Workspace identity and the current verified role appear above the forms.
- Use Awaiting Approval as the only approval workflow; do not repeat a manual email approval form.
- Member controls span the full panel width after the registration link.
- Use labeled controls with at least 44px height; purpose uses a resizable textarea.
- Keep status feedback above the forms. Retain verified-email approval guidance.
- Use restrained red styling for revocation and an explicit text label.
- Display governance events in a full-width chronological list with readable timestamps.
- Collapse platform workspace creation by default; preserve server-enforced role boundaries.
- Keep pagination state in a lightweight store. Show Previous/Next only when lists exceed 50 records.

Workspace details are read-only in the banner. Owners and Platform Admins open
a labeled modal using Edit Details; Cancel closes without persisting changes.

Use a neutral border without a colored accent on the workspace banner. Align
labels and values in rows; stack them on small screens. Put role, counts, and
Edit Details in a separated footer, with a neutral role badge.

Awaiting Approval uses AgGrid with searchable verified emails, UTC request times,
and per-row Grant Role and Approve/Reject dropdowns. Selecting a decision submits that row; optional decision notes can be edited in the grid. A workspace registration link routes signup
requests without granting membership. Banner counts represent undecided requests.
