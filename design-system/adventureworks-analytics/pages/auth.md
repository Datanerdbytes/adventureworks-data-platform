# Authentication pages

- Use the dashboard's blue primary, slate text, pale background, and white cards.
- Login uses a horizontal 900px card with a navy brand panel and a white form panel.
  Below 640px, stack a compact brand header above the form; hide decorative artwork.
  Other auth screens use a compact single-column 440px card.
- Use 32px panel padding (40px on wide screens), reduced to 24px on mobile.
- AdventureWorks AW mark and wordmark lead; 28px title follows.
- Visible labels, 48px controls, password-manager support, keyboard focus rings.
- Forgot Password beside the password label; Create Account below login options.
- Full-width, equally prominent white provider buttons with official brand logos.
- Hide provider group and divider until configured providers are available.
- Empty status messages occupy no space; errors use an announced inline alert.
- No marketing paragraphs or retry button on the ordinary sign-in page.

Provider artwork is stored locally to avoid external image requests:

- Google: https://developers.google.com/identity/branding-guidelines
  (official Google G PNG, unchanged).
- GitHub: https://brand.github.com/foundations/logo
  (official GitHub Invertocat Black SVG, unchanged).

Successful email/password signup clears both fields while keeping the email
confirmation guidance visible. Failed signup retains the
editable values; signup never creates an application session. Confirmed active accounts can then sign in without workspace approval.

Password fields include visible Show/Hide controls with aria-pressed state and password-manager autocomplete. Recovery uses a PKCE code in the requesting browser, an isolated session and bound identity.
