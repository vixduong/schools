# Design: School Platform

The locked system. Every Hallmark run reads this first and every screen shares it. Change it on purpose; the file is the rule. Specimen: `docs/design/specimen/index.html`. Reference plates: `docs/design/reference/` (statechart-art by Kevin Ngo).

## System
- Genre: editorial, applied as an app (`shape: app screen` on every screen)
- Theme: custom (vibe: "a teacher's ledger, pen and coloured pencil")
- Idea: every record with a lifecycle is a pinned ticket on a statechart, drawn on paper in pen and pencil
- Axes: light/slab-serif/cool · posture: restrained
- Waiver carried by every build: `waive 65` (cream paper and slab display come from the reference the owner chose)

## The brand layer, and where it stops
- **Ticket**: shows the state of a record that moves through a workflow (gradebook, leave request, report card, enrollment). Ticket stock on paper, 1.5px ink edge, hatched offset shadow, a pin on the top edge, the state word in the display face. Nothing else gets the hatch.
- **Pins** carry state, always beside the state's word: blue open, gold waiting, ink locked, red needs action.
- **Statechart**: a workflow is drawn as tickets joined by pen lines with italic labels; the path that needs a reason (reopen a locked gradebook) is red ink. Draw only real workflows.
- **Pencil regions**: one pastel per Level (Preschool gold, Primary green, Lower Secondary blue, Upper Secondary rose), used where Levels sit side by side or to mark which Level a screen belongs to. Never as decoration.
- **Red ink** means error, warning or the reason-required path. Never a brand colour.
- **Working surfaces stay plain**: tables, forms and lists use the body face, horizontal hairlines, tabular figures, no hatch, no pins inside rows.
- **Illustration**: hand-drawn art in the reference's style, commissioned from an illustrator, only for empty states, onboarding, the parent portal and Preschool. Never drawn in code, never AI-generated.

## Tokens
`docs/design/specimen/tokens.css` is the source of truth. The roles:
```css
:root {
  --color-paper: oklch(96.2% 0.012 85);  --color-paper-2: oklch(98.6% 0.008 90);  --color-paper-3: oklch(92.6% 0.016 80);
  --color-ink: oklch(25% 0.012 65);  --color-ink-2: oklch(38% 0.012 65);  --color-muted: oklch(49% 0.014 70);  --color-rule: oklch(84% 0.018 80);
  --color-accent: oklch(44% 0.13 255);  --color-accent-ink: oklch(98.6% 0.008 90);  --color-focus: oklch(46% 0.19 258);
  --color-error: oklch(51% 0.19 25);  --color-error-wash: oklch(95.5% 0.025 20);  --color-success: oklch(47% 0.11 150);
  --color-pin-open / -waiting / -locked / -alert;  --color-level-pre / -pri / -lower / -upper (+ -edge);
  --font-display: "Hepta Slab", ui-serif, Georgia, serif;   /* weight 300, roman only */
  --font-body: "Be Vietnam Pro", ui-sans-serif, system-ui, sans-serif;   /* 400, 600, italic 400 */
  --radius-ticket: 2px;  --radius-control: 6px;  --radius-card: 10px;  --rule-hair: 1px;  --rule-pen: 1.5px;  --shadow-card: none;
}
```
Both faces ship a Vietnamese subset; any replacement face must too. Type scale ratio 1.2 from a 16px body; spacing, easings and durations live in `tokens.css`.

## Type
- Display face for page titles, section heads and ticket state words only, weight 300.
- Body face for everything people work in: tables, labels, buttons, data. Labels sentence case, never tracked capitals.
- Italic body for annotations: transition labels, helper notes, the line under a section head.
- Figures: `tabular-nums`, Vietnamese decimal comma (`7,9`).

## Controls
- Height 36px, hit target 44px, radius 6px, one filled primary per screen.
- Primary: pen-blue fill. Secondary: 1.5px ink outline. Quiet: underlined text. Destructive: red-ink outline.
- Inputs: 1px muted edge, inset focus ring, error = red edge + red wash + message under the field.
- Every data region draws four states: loading (skeleton), empty (what goes here, one action), error (what broke, what to do), full.

## Dense components (specimen: `docs/design/specimen/components.html`)
- **Data table**: a filter row above (search, selects, density toggle Gọn/Thoáng); sortable heads are buttons with `aria-sort`; the header sticks under the top bar; the selection is a pen-blue wash (`--color-select`) with a bulk bar above stating the count; a warning value is red ink, its label a red-outlined tag; pagination states the range in words. No zebra stripes, no outer border. On phones the name column pins and the scores scroll sideways.
- **Select**: a native `<select>` up to about seven options; beyond that a combobox (typing filters, the match underlined in pen blue, the active row on `--color-paper-3`, the chosen one bold with a tick); multi-select is chips inside one field box, removed by x or Backspace.
- **Date and time**: dates are `dd/mm/yyyy`, weeks start on Monday (T2 to CN), times are 24-hour, typed straight in. The calendar popover: today outlined in ink, the picked day filled pen blue, days outside the month and Sundays muted, a gold dot on days that already have an event (the waiting-pin colour). A range shows both ends and errors when the end precedes the start. In shadcn this is `Calendar` (react-day-picker) with the `vi` locale and `weekStartsOn: 1`.

## Dark mode
- Same hues, re-derived lightness in `tokens.css` (`[data-mode="dark"]` plus `prefers-color-scheme`): paper L 17, raised surfaces lighter (L 21), wells darker (L 14); ink L 93; pen blue lifts to L 72 with dark text on it; red ink to L 69; Level pastels become deep fills with light edges; the hatch drops to 30% ink. No drop shadows.
- Toggle sets `data-mode` on `<html>`, stored in `localStorage`, read before first paint.

## Motion
- Character: still. Colour and a 1px press only; no reveals; reduced motion turns the spinner static.

## Exports: Tailwind v4 + shadcn/ui
```css
@import "tailwindcss";
@import "./tokens.css";
@import "./base.css" layer(base);
/* shadcn reads its own names; point them at ours */
:root {
  --background: var(--color-paper); --foreground: var(--color-ink);
  --card: var(--color-paper-2); --card-foreground: var(--color-ink);
  --popover: var(--color-paper-2); --popover-foreground: var(--color-ink);
  --primary: var(--color-accent); --primary-foreground: var(--color-accent-ink);
  --secondary: var(--color-paper-3); --secondary-foreground: var(--color-ink-2);
  --muted: var(--color-paper-3); --muted-foreground: var(--color-muted);
  --accent: var(--color-paper-3); --accent-foreground: var(--color-ink);
  --destructive: var(--color-error); --border: var(--color-rule); --input: var(--color-muted); --ring: var(--color-focus);
  --radius: var(--radius-control);
}
```
shadcn's `--color-accent` and `--color-muted` mean a hover surface and a quiet background. In the app's `@theme`, expose ours as `--color-pen` (accent) and `--color-ink-3` (muted) so the names do not collide. The ticket, pin and Level region become three house components (`<StateTicket>`, `<Pin>`, `<LevelRegion>`) on top of shadcn.
