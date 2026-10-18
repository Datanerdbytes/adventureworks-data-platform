# Dark mode review

Reviewed 2026-10-19 against the installed
[dark-mode-design-expert](../.agents/skills/dark-mode-design-expert/SKILL.md).
`skills-lock.json` records `curiositech/some_claude_skills` as its source;
`.claude/skills/dark-mode-design-expert` points to that installed copy.
The repository-required ui-ux-pro-max contrast guidance and existing design system
were also applied.

## Findings corrected

- Settings declared two callback outputs but returned one object, preventing
  valid preference updates. It now returns one preferences object and waits for
  hydration before saving.
- Theme application depended on Settings being mounted. All page shells now run
  the shared preference script before stylesheets; new browsers default to Light,
  explicit overrides persist, and explicit System/storage changes update appearance.
- Chart code passed layout properties to `Plotly.restyle`, targeted one trace,
  and ran only on theme changes. The replacement uses `Plotly.relayout` after
  rendering, including new/filtered figures and secondary axes. It consumes CSS
  tokens without changing data, ranges, zoom, or series colors.
- Generic dropdown controls and menus lacked dark surfaces. Control boundaries,
  primary-button text, landing captions, and login branding needed contrast fixes.
- The palette was duplicated between CSS and Python, and overlays used the same
  surface as cards. Semantic tokens now live in `theme.py`; cards and overlays use
  progressively lighter navy surfaces.

The existing navy palette, off-white text, brighter blue/teal accents and native
`color-scheme` follow the skill. Its atmospheric/weather examples are optional;
the analytics console keeps its established layout and branding.

## Verification

- 246 offline Python tests passed, including dark token contrast and pre-paint
  integration tests.
- 30 authentication JavaScript tests passed.
- Eight theme JavaScript tests passed: system/explicit preferences, persistence,
  cross-tab updates, unavailable storage, chart rerenders, annotation contrast
  when switching appearances, and Settings hydration.
- Ruff, Black, mypy, Prettier and JavaScript syntax checks passed for relevant files.
- Token checks require 4.5:1 for normal text/accent pairs and 3:1 for control borders
  against every defined dark surface, plus increasing surface luminance.
- Visually inspected an offline login preview using the actual templates and CSS.
  The preview excludes authentication JavaScript and makes no service requests.

Run the theme checks with:

```sh
node --test scripts/test_theme.test.mjs
uv run --locked python scripts/pre_commit_checks.py python-tests
npm run test:auth
```

This review does not establish full authenticated browser behavior, production
appearance/deployment, every chart's rendered contrast, color-blind perception,
or OLED/LCD and outdoor/low-brightness device behavior. Those portions of the
skill's checklist require further browser/device verification.
