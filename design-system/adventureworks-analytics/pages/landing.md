# Landing page override

Reference: user-supplied DataPulse screenshot (October 2, 2026).

- Rounded white navigation panel, pale blue/lavender atmosphere.
- Bold sans-serif hero with blue-to-purple gradient emphasis.
- Green primary CTA (#128147 for readable white text), blue outlined secondary.
- Two-column hero with tilted code-native SVG analytics preview and floating notes.
- On narrow screens, stack copy above preview; preserve sign-in access.
- Feature cards, three-step workflow, closing CTA, and compact footer.
- AdventureWorks branding; illustrative data explicitly labeled synthetic.
- Open workspace points to protected /dashboard; Explore features scrolls to #features.
- Do not advertise a trial, live synchronization, customer counts, pricing, or integrations that do not exist.

The original dashboard theme remains in effect inside the workspace. Its bottom
sidebar control is now an authenticated account avatar with a chevron disclosure;
collapse is available inside that disclosure and on Settings.

## Motion

On page load, the analytics illustration gently fades and floats into place over
4.6 seconds. Callouts settle over 3.8 seconds after a 0.2-second delay. Each plays
once, preserving the existing tilt and avoiding an endless distracting loop.
Only opacity and translation animate; reduced-motion users see the static view.
