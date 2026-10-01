# AdventureWorks Analytics design system

Approved direction: a light internal data console inspired by the supplied
Lakebase screenshot. Original AdventureWorks branding; no copied vendor assets.

- Background #F5F7FA; white surfaces; text #243B45; muted #596B78.
- Primary #2274B5; secondary chart series #138579; borders #DFE6ED.
- System sans-serif, 16px base, compact 13–14px controls, 28px page headings.
- 8px spacing basis and card radius; 24px card gaps; restrained shadows.
- Header 72px; desktop sidebar 248px expanded / 72px collapsed.
- Mobile breakpoint 768px; accessible modal navigation drawer below it.
- White bordered cards, thin grid lines, blue/teal charts with legends.
- Explicit demo labels; no controls that imply a real connection or pipeline run.
- Visible keyboard focus; labeled icon controls; reduced motion support.

The UI UX Pro Max search matched data-dense dashboard styling and keyboard
navigation guidance. Its unrelated enterprise marketing/landing-page pattern
was rejected; the reference and approved console plan govern layout and color.
Dash is not among its stack presets; implementation follows Dash APIs and the
repository conventions. Runtime visual constants are centralized in theme.py.
