# Settings

Use a desktop preferences layout inspired by the supplied Codex settings reference,
within the existing Dash shell and AdventureWorks theme.

- Group related settings into Appearance, Layout & tables, Accessibility,
  Data & exports, Notifications, and About.
- On wide desktops, show an in-page category rail beside a single column of
  bordered groups. Below 1100px, wrap category links above the content.
- Each row has a title and explanatory text on the left and its control on the
  right. Stack non-binary controls when the content column is under 600px.
- Use DBC switches for binary preferences. Use native radio-based segmented
  controls for the existing two- or three-choice preferences. Dropdowns are
  reserved for larger option sets; no current preference needs one.
- Keep touch targets at least 44px, semantic group names, associated switch
  labels, visible keyboard focus, natural wrapping, and reduced-motion support.
- Reuse semantic colors for light and dark surfaces. Keep styles in settings.css.
- Hydrate controls without saving defaults on entry. Switches translate their
  booleans to the existing on/off storage values; preserve unknown stored fields.
  Sidebar collapse is an explicit boolean setting, not an inversion action.
- Clearly distinguish browser preferences awaiting support from active features.
  Do not imply live notifications, currency conversion, or export behavior that
  is not connected. Keep demo metadata labeled as sample-data information.
