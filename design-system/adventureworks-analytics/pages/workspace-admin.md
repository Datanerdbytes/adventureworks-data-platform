> Retired on 2026-10-19. The current account directory follows [User Management](user-management.md). This document records the prior workspace governance design.

# Workspace Administration

Follow MASTER.md and the existing Dash/DBC console styling.

- Two columns of white bordered panels on wide desktops, one column below 1100px.
- Workspace identity and the current verified role appear above the forms.
- Use Awaiting Approval as the only approval workflow; do not repeat a manual email approval form.
- Move member search and access management to `/workspace/admin/members`, linked by View members. Keep the overview focused on workspace identity, registration, approval requests, and activity.
- Use labeled controls with at least 44px height; purpose uses a resizable textarea.
- Keep status feedback above the forms. Retain verified-email approval guidance.
- Use restrained red styling for revocation and an explicit text label.
- Display governance events in compact rows with action, actor email, and UTC timestamp. Page through five events at a time; use a separate activity offset from approval requests.
- Keep creation on `/workspace/admin/create`, linked by a platform-admin-only Create workspace action. Preserve server-enforced role boundaries.
- Keep pagination state in lightweight stores. Approval requests use 50 rows per page; member search uses 10 and activity uses 5. Show range/count and disable unavailable Previous/Next actions.

Workspace details are read-only in the banner. Owners and Platform Admins open
a labeled modal using Edit Details; Cancel closes without persisting changes.

Use a neutral border without a colored accent on the workspace banner. Align
labels and values in rows; stack them on small screens. Put role, counts, and
Edit Details in a separated footer, with a neutral role badge.

Awaiting Approval uses AgGrid with searchable verified emails, UTC request times,
and per-row Grant Role and Approve/Reject dropdowns. Selecting a decision submits that row; optional decision notes can be edited in the grid. A registration card sits to the left of Current Workspace on wide screens,
and stacks above it below 1100px. Show a locally generated black-and-white QR
code with its quiet zone, a Copy registration link button, and a brief reminder
that email verification and workspace approval are required. Do not display a
long URL field. The code routes signup requests without granting membership. Banner counts represent undecided requests.

## Create workspace

Use a dedicated page inside the existing dashboard shell. Keep a visible return
link to Workspace Admin and a Cancel action. Group workspace name, responsible
team, and optional purpose before initial owner email. Required/optional labels,
visible helper text, inline validation, and submission feedback support completion.

Use the existing white bordered panel, blue primary action, 44px controls, and
shared theme tokens. A compact secondary guide explains verified owner access,
the switch to the new workspace, member registration, and shared analytics data.
Stack the guide beneath the form below 1100px and actions below 600px. Disable
submission while pending. No signup, invitation, or warehouse changes are implied.

## Members

Use the existing dashboard shell with a return link to Workspace Admin. Put
workspace, email search, role, and access filters above a single-select AgGrid.
Filters apply to the whole authorized result set through Supabase, with ten
memberships per page. All managed workspaces includes only workspaces the actor
can administer. Disable local grid sorting/filtering to avoid implying that a
single returned page represents all results.

Open member details in a labeled modal with canonical email, workspace, verified
email status, joined/updated timestamps, and user ID. Role and access controls
retain the existing transactional governance checks. Admins can change other
Viewers only; show higher roles read-only. Preserve the last active Owner guard.

Stack filters on small screens, keep touch targets at least 44px, and contain
wide table scrolling within the grid. Clear selection when filters or pages
change. Show empty and service-failure states without stale member rows.

Successful member edits close the modal and refresh the directory in place,
preserving its filters and page where possible. Clear row selection and show
success above the filters. If the last matching row disappears, return to the
last available page. Changes to the actor's own current-workspace membership
reload the authorized workspace shell; ordinary edits do not navigate away.
