# What are the design conventions of the brand layer, built with /hallmark?

Type: prototype
Status: claimed
Blocked by:

## Question

Using /hallmark and the reference images in `docs/design/reference/`, define the design system: color tokens (paper, ink, red ink, pastel region fills per Level/role), typography (typewriter serif for headings, italic labels, sans with tabular numbers for data), the pinned ticket card for states, region panels, borders/shadows (hand-drawn offset hatch), spacing, density for data tables, illustration rules, accessibility (contrast on pastel fills, focus states). Must map onto Tailwind tokens + shadcn/ui. Output: `docs/design/DESIGN.md` and a specimen page linked from this ticket.

## Comments

- Draft built with /hallmark (custom direction, app scope): `DESIGN.md` at the repo root (locked system + Tailwind v4/shadcn mapping), specimen `docs/design/specimen/index.html` with `tokens.css`, `base.css`, `specimen.css`; screenshots in `docs/design/specimen/.hallmark/shots/`. sloplint: 0 FAIL, 0 WARN. Finish review (subagent): 8 findings, 5 fixed, 3 kept by decision (listed in the CSS stamp). Waiting on the owner's reaction before resolving.
