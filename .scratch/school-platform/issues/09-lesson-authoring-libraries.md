# Which libraries can teachers use to build lesson content for maths, geometry, physics, chemistry and biology?

Type: research
Status: resolved
Blocked by:

## Question

Lesson authoring needs subject content beyond rich text: formulas, geometry constructions, function graphs, physics simulations, chemical formulas, equations and structures, biology diagrams and molecules. For a React SPA with a Django API, sold as multi-tenant SaaS to Vietnamese schools, which libraries or embeddable tools cover each subject? For each candidate: licence and whether it allows commercial SaaS use (GeoGebra, Desmos, ChemDoodle and PhET carry conditions), self-hosting versus a third-party CDN or API, React integration, the stored data format (can a lesson be saved as portable JSON in our database?), print/PDF and Word export, Vietnamese text inside figures, accessibility, and maintenance health. Also: which rich-text editor framework (Tiptap/ProseMirror, Lexical, BlockNote, etc.) can host these as embedded blocks, and what does the same content need in order to be reused in the exam bank. End with a recommended minimal set per subject and what to leave out.

## Answer

Findings: branch `research/lesson-authoring-libraries`, file `docs/research/lesson-authoring-libraries.md`. Licences for GeoGebra (commercial needs a paid agreement), JSXGraph (MIT or LGPL) and Ketcher (Apache-2.0) spot-checked by the main session.

- Editor: Tiptap (MIT) with custom React node views; a lesson is stored as Tiptap JSON in Postgres `jsonb`. Each subject node keeps its editable source plus an SVG snapshot, so print, Word and the exam bank reuse it.
- Recommended minimal set: maths KaTeX + Tiptap Mathematics (+ MathLive for input), all MIT; chemical equations via KaTeX mhchem `\ce`; geometry, graphs and simple physics with JSXGraph (we define our own JSON board spec, as it has none); chemical structures with Ketcher (KET JSON + molfile + SVG); biology as labelled images, 3Dmol.js (BSD-3) only for 3D molecules.
- Left out for licence or cost: GeoGebra, Desmos, ChemDoodle (GPLv3/commercial), live PhET sims (new terms from 2026-03-29), Mol*, tldraw, BlockNote and Tiptap Pro export.
- Export: build it. Word via Pandoc (editable OMML equations) or the `docx` library; PDF from the static renderer and a headless browser. Exam questions use the same node types, with answers for auto-grading in plain fields.
- Open: Desmos and PhET terms and pricing; Ketcher and JSXGraph SVG export APIs; Vietnamese diacritics inside each tool; legal review of running Pandoc (GPL) as an external process.
