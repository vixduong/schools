# Lesson authoring libraries for maths, geometry, physics, chemistry and biology

Ticket: `.scratch/school-platform/issues/09-lesson-authoring-libraries.md`
Research date: 2026-10-31. Versions and release dates are from the npm registry (`https://registry.npmjs.org/<pkg>`) and GitHub release APIs, read the same day.
Context: multi-tenant SaaS sold by subscription (a commercial use), React SPA + Django/DRF + Postgres, S3-compatible files.

"Not verified" marks anything I could not read at the primary source. Licences are not legal advice; have counsel confirm before launch.

## 1. Bottom line

| Subject | Use | Licence | Leave out |
|---|---|---|---|
| Editor | Tiptap (ProseMirror) core + custom React node views, content stored as JSON | MIT | Tiptap Pro Conversion for export (paid), BlockNote XL exporters (GPL or paid), Lexical (no first-party math/block ecosystem) |
| Formulas | KaTeX render + `@tiptap/extension-mathematics` + MathLive for typing | MIT | MathJax (heavier, only if KaTeX lacks a macro) |
| Chemical formulas and equations | KaTeX `mhchem` (`\ce{}`) | KaTeX MIT; mhchem MIT per KaTeX contrib (not verified separately, see 3.4) | none |
| Geometry and function graphs | JSXGraph (one library for both) | MIT OR LGPL-3.0 (choose MIT) | GeoGebra, Desmos |
| Physics | JSXGraph diagrams and graphs now; PhET only after a written licence | see 3.6 | Embedding live PhET sims in v1 |
| Chemical structures | Ketcher (editor) + SVG snapshot | Apache-2.0 | ChemDoodle Web (GPLv3 or paid), Kekule.js (optional alternative) |
| Biology | Images/SVG with label overlays; 3Dmol.js only for 3D molecules | 3Dmol BSD-3-Clause | Mol*, tldraw, whiteboards |

Rule used: pick the smallest set where every item can be stored as portable JSON in Postgres, rendered statically for print, and reused in the exam bank.

## 2. Editor framework

| Framework | Latest (npm, 2026-10-31) | Licence | JSON storage | Verdict |
|---|---|---|---|---|
| Tiptap (`@tiptap/core`, `@tiptap/react`) | 3.32.2 (released 2026-10-30) | MIT (npm metadata) | `editor.getJSON()` / `setContent(json)` | Recommended |
| BlockNote (`@blocknote/core`) | 0.57.0 (2026-10-30) | core MPL-2.0; XL packages GPL-3.0 OR PROPRIETARY | block JSON | Possible, but export is the paid part |
| Lexical (`lexical`) | 0.53.0 (2026-10-28) | MIT | serialised editor state JSON | Not chosen: no maintained math/chemistry node set found; you would build every block |

Sources:
- Tiptap persistence: "Since Tiptap is able to return HTML or JSON you can easily save the content to a database" and "we recommend using JSON to persist the editor state". https://tiptap.dev/docs/editor/core-concepts/persistence
- Tiptap custom React node views: https://tiptap.dev/docs/editor/extensions/custom-extensions/node-views/react
- Tiptap Mathematics: stores `latex` per node, has inline and block nodes (`insertBlockMath({ latex })`), renders with KaTeX, and ships a migration helper for `$...$` strings. https://tiptap.dev/docs/editor/extensions/nodes/mathematics (package `@tiptap/extension-mathematics` 3.32.2, MIT, npm).
- Server-side JSON to HTML: `@tiptap/static-renderer` 3.32.2, MIT (npm). Useful for print pages and PDF.
- BlockNote pricing page: "The core library is licensed under the MPL 2.0 license, which allows you to use BlockNote in commercial and closed-source applications - even without a subscription." and "The XL packages (like AI integration, multi-column layouts, and exporters) are dual-licensed and available under GPL-3.0, or - for closed-source projects - a commercial license as part of the BlockNote Business subscription or above." Business is listed at 195 USD/month (390 struck through, "-50%"; 2,340 billed yearly). https://www.blocknotejs.org/pricing
  `@blocknote/xl-docx-exporter` and `@blocknote/xl-pdf-exporter` 0.57.0: licence field `GPL-3.0 OR PROPRIETARY` (npm).
- Tiptap Conversion (DOCX/PDF/ODT export, DOCX import) is "a Pro package included with all Tiptap subscriptions", needs Tiptap's private npm registry, marked Beta. https://tiptap.dev/docs/conversion/import-export/docx Price not read; not verified.

### Block model (recommended storage)

Store the lesson as Tiptap/ProseMirror JSON in a Postgres `jsonb` column. Each subject widget is one custom node with small, versioned attributes:

```json
{"type":"mathBlock","attrs":{"latex":"\\frac{a}{b}"}}
{"type":"geometryBoard","attrs":{"v":1,"spec":{...}, "svg":"s3://.../fig.svg", "alt":"..."}}
{"type":"molecule","attrs":{"v":1,"ket":{...}, "svg":"s3://.../mol.svg", "alt":"..."}}
```

Rules that make later reuse cheap:
1. Keep the editable source (LaTeX, JSXGraph spec, KET JSON) and a rendered SVG snapshot in the same node. Print, PDF, Word and the exam bank read the SVG; the editor reads the source.
2. Put a `v` (schema version) on every node so old lessons can be migrated.
3. Store images/SVG on S3 and reference by key, not inline base64.
4. Treat widget JSON as your own schema. Do not store third-party opaque state where you can avoid it (see Desmos and GeoGebra below).

## 3. Per-tool findings

### 3.1 GeoGebra (geometry, graphs): excluded

- Licence, from GeoGebra's own legal repo: "You are free to copy, distribute and transmit GeoGebra for non-commercial purposes." and "Any use of GeoGebra for a commercial purpose is subject to and requires a special license. If you intend to use GeoGebra for a commercial purpose, please contact office@geogebra.org to arrange a License and Collaboration Agreement with us." https://github.com/geogebra/legal/blob/main/geogebra_license.md (page on geogebra.org/license says terms updated November 2025)
- Their examples of commercial use include "use of GeoGebra ... to generate or develop educational materials or resources which will be sold in exchange for a fee (including course or tuition fees)". Same file. A subscription authoring product falls under this wording.
- Non-commercial licence: "you only do so for non-commercial purposes (without charging a fee to any third party)", and must show "Made with GeoGebra(R)". Same file.
- Source code is EUPL v1.2, but "any use of the source code together with the Materials and/or the Language Files ... as part of the GeoGebra product remains subject to the remaining terms of this License and must be used for non-commercial purposes only." Same file.
- Technical facts if a commercial agreement were ever signed: self-host bundle exists (https://geogebra.github.io/docs/reference/en/GeoGebra_Apps_Embedding/), API has `getXML()`, `getFileJSON()`, `getPNGBase64()` (https://geogebra.github.io/docs/reference/en/GeoGebra_Apps_API/). Fee not published; not verified.
- Decision: do not ship without a signed agreement. JSXGraph covers the need.

### 3.2 Desmos API (graphs): excluded, terms not verified

- Verified from docs v1.11: API key required as URL parameter; "partners" may self-host; stable versions released yearly in April; `getState()` returns an object that can be `JSON.stringify`-ed, but "Calculator states should be treated as opaque values". Four-function, scientific and geometry tools must be enabled per key. https://www.desmos.com/api/v1.11/docs/index.html
- Not verified: the API Terms of Service (https://www.desmos.com/api-terms is a JavaScript page that did not render for me), pricing, and whether a paid SaaS is allowed. The docs only point to https://www.desmos.com/my-api "partnership options".
- Decision: out. Opaque state and an unreviewed partner agreement are both against the "portable JSON" requirement.

### 3.3 JSXGraph (geometry and function graphs): recommended

- Latest 1.14.2, released 2026-10-26 (GitHub releases API); npm licence `(MIT OR LGPL-3.0-or-later)`; README: "free software dual licensed under the GNU LGPL or MIT License". https://github.com/jsxgraph/jsxgraph ; MIT file: https://raw.githubusercontent.com/jsxgraph/jsxgraph/master/LICENSE.MIT
- MIT text allows commercial use provided the copyright and permission notice are kept.
- Self-hosted, no third-party CDN needed. Draws points, lines, circles, polygons, function graphs, sliders, and works on SVG.
- React: no official React wrapper found in the README (not verified for third-party wrappers). Mount in a `useEffect` inside a Tiptap React node view.
- Stored format: JSXGraph has no portable board file I could confirm. Store your own `spec` (list of elements: type, parents, attributes) and rebuild the board from it. This is the main cost of choosing it. Not verified: any built-in board serialisation.
- Print/export: SVG renderer; capture the board's SVG node as the snapshot. Not verified: a documented SVG export API.
- Vietnamese text in figures: labels are plain text/HTML strings, so Unicode is expected to work; not verified by test.
- Accessibility: figure needs a hand-written `alt` and a text description; the library is not accessible on its own (not verified in docs).

### 3.4 KaTeX, MathJax, mhchem, MathLive (formulas, chemical equations)

| Tool | Latest (npm) | Licence | Role |
|---|---|---|---|
| KaTeX | 0.19.1, 2026-10-23 | MIT ("Copyright (c) 2013-2020 Khan Academy and other contributors") | Render LaTeX, fast, server-side capable |
| MathJax | 4.1.3, 2026-07-03 (`mathjax`) | Apache-2.0 | Alternative renderer; MathJax 3 npm package `mathjax-full` last 3.2.2, 2022 (old) |
| mhchem for KaTeX | ships in KaTeX `contrib/mhchem`, version-matched to KaTeX | MIT as part of KaTeX repo (the standalone MathJax-mhchem repo is Apache-2.0 per GitHub API) | `\ce{H2O}`, `\ce{2H2 + O2 -> 2H2O}`, `\pu{}` |
| MathLive | 0.111.1, 2026-10-09 | MIT (npm; LICENSE file says "Copyright (c) 2017 - present Arno Gourdol" and the usual permission grant) | Visual math input for teachers; outputs LaTeX |

- KaTeX mhchem extension: "This extension adds to KaTeX the `\ce` and `\pu` functions from the mhchem package ... This extension isn't part of core KaTeX, so the script should be separately included." https://raw.githubusercontent.com/KaTeX/KaTeX/main/contrib/mhchem/README.md ; with npm: `import "katex/contrib/mhchem"`.
- Why this pair: one LaTeX string is the stored form (`latex` attr in Tiptap). The same string works in the exam bank and can be converted to Word math (section 5).
- Vietnamese text inside formulas: use `\text{...}` with Unicode; KaTeX `\text` accepts Unicode but I did not test combining diacritics. Not verified.
- Accessibility: KaTeX output includes MathML for screen readers by default (not verified for 0.19 in docs I read).
- MathLive adds a virtual keyboard useful on tablets; it is optional. If the team wants fewer parts, a plain LaTeX field with live KaTeX preview is smaller.

### 3.5 Chemistry structures: Ketcher recommended; ChemDoodle and Kekule.js not chosen

| Tool | Latest | Licence | Notes |
|---|---|---|---|
| Ketcher (`ketcher-react`) | 3.18.0, 2026-09-02 | Apache-2.0 (repo sidebar and LICENSE; "Copyright (c) 2021 EPAM Systems, Inc.") | Open source, active (7,701 commits). React `Editor` component with `StandaloneStructServiceProvider` (runs in the browser, no server). Formats: `getKet()` (native JSON), `getMolfile()` (V2000/V3000), `getSmiles()`. https://github.com/epam/ketcher |
| ChemDoodle Web Components | version not read | GPLv3 or paid proprietary | see below |
| Kekule.js | 1.0.4, 2026-05-22 | MIT (GitHub licence API; repo LICENSE "MIT License, Copyright (c) 2017 Chen Jiang") | Works, smaller community (280 stars, GitHub API); not React-first |
| SMILES Drawer | 2.4.1, 2026-06-26 | MIT | Viewer only, small; alternative for display |
| OpenChemLib / RDKit.js | 9.25.2 / 2026.9.1 | BSD-3-Clause | Only if the exam bank needs structure matching/search; skip for v1 |

- ChemDoodle licence, quoted: "The ChemDoodle Web Components library is licensed under version 3 of the GNU GENERAL PUBLIC LICENSE. If you want to include ChemDoodle Web Components in your product or website, you must abide by this license, or contact us for a proprietary license." and "Can I use the ChemDoodle Web Components in my proprietary product? Not under the GPLv3 license as it is incompatible with proprietary products. Contact us for a proprietary license instead". https://web.chemdoodle.com/installation/license . Proprietary price not published ("Contact us right now for options"); SVG export and condensed labels are listed as proprietary-only features. https://web.chemdoodle.com/store/proprietary-licensing . Excluded.
- Ketcher stored format: store `ket` JSON plus a molfile string and an SVG snapshot. Ketcher's image export API was not verified; if missing, render the molfile with SMILES Drawer or OpenChemLib for the static snapshot.
- Vietnamese UI for Ketcher: not verified. Atom labels are chemical symbols and need no translation.
- Accessibility: structure images need a text alternative (name, formula as `\ce{}`).

### 3.6 PhET (physics, also chemistry/biology): do not embed live in v1

- Sims published before 2026-03-29 ("Historical PhET Simulations"): "published under the Creative Commons Attribution 4.0 License (CC BY 4.0)", "may be freely used and/or redistributed by third parties for non-commercial or commercial purposes". Conditions: "Attribution must appear as close as possible to the point of use and be human-readable", the text "Simulation by PhET Interactive Simulations, University of Colorado Boulder, licensed under CC BY 4.0," with the URL; "The PhET logo must remain visible, unobstructed, and unaltered." The page marks this version "outdated and no longer maintained". https://phet.colorado.edu/en/licensing/html
- Sims published on or after 2026-03-29, PhET-iO, Java, Flash are excluded from that page: "The Regular HTML Simulation Files ... published after March 29, 2026" and it redirects to https://phet.colorado.edu/en/licensing . That page is a JavaScript app that did not render for me, so the current terms are **not verified**.
- PhET help centre: "all commercial use of PhET simulations requires a commercial license from the University of Colorado Boulder" and commercial use is "any use that provides commercial advantage or monetary compensation". https://phet.colorado.edu/en/help-center/getting-started . Our product charges subscriptions, so this wording is likely to apply to current sims.
- A "PhET Studio / Premium for classroom use" paid licence agreement exists (PDF, created 2025-06-20, section titles only readable). https://phet.colorado.edu/assets/legal/phet-premium-for-classroom-use-license-purchase-agreement.pdf . Terms, price and whether it covers a SaaS reseller: not verified.
- Self-hosting a frozen pre-2026-03-29 copy under CC BY 4.0 looks permitted by the quoted text, but the copy ages, loses fixes, and the page explicitly says it is no longer maintained. Treat as an optional later step after legal review, not a v1 dependency.
- Vietnamese translations of PhET sims: widely reported but not verified here.
- Decision: physics v1 = JSXGraph (vector diagrams, motion graphs with sliders) plus images/SVG. Ask PhET for a commercial quote if teachers demand simulations.

### 3.7 3Dmol.js and Mol* (biology/chemistry 3D molecules)

- 3Dmol.js 2.5.5, 2026-05-22; BSD-3-Clause ("3Dmol.js incorporates code from GLmol, Three.js, and jQuery and is licensed under a BSD-3-Clause license."). https://raw.githubusercontent.com/3dmol/3Dmol.js/master/LICENSE
- Mol* (`molstar`) 5.13.1, 2026-10-08; MIT ("Copyright (c) 2017 - now, Mol* contributors"). https://raw.githubusercontent.com/molstar/molstar/master/LICENSE
- Both read PDB/mmCIF; store the PDB ID or the file on S3 plus camera/style attributes. 3Dmol is lighter. Mol* is heavier and aimed at research-scale data; leave out unless 3Dmol falls short.
- Mount inside a node view; needs WebGL, so provide the SVG/PNG snapshot for print (snapshot API not verified).

### 3.8 Biology diagrams

No dedicated biology library was needed. Teachers upload labelled images/SVG; add a "labelled figure" node: image key on S3 + array of `{x,y,text}` labels in percent coordinates. Exports as the same image with labels burned in or as a table. Also seen and left out: tldraw 5.6.0 (licence "SEE LICENSE IN LICENSE.md", terms not read; not verified), Excalidraw 0.18.1, 2026-04-20, MIT (usable, but a drawing app is more than a v1 lesson needs).

## 4. Reuse in the exam bank

- A question is a Tiptap JSON document using the same node types (stem, options, answer, explanation). Because math, chemistry and figures are nodes holding source plus snapshot, a lesson block can be copied into a question without conversion.
- Store the question body as `jsonb` and index separately: subject, grade, topic, difficulty, the list of node types used, and a plain-text extraction (LaTeX included) for search.
- Auto-gradable answers should not depend on the widget. Store numeric/choice/LaTeX answers as plain fields. Interactive widgets (JSXGraph board, Ketcher drawing) stay display-only in exams in v1.
- Keep every node's `v` and a snapshot so an exam printed in 2027 renders the same after library upgrades.

## 5. Print, PDF and Word export

- HTML/PDF: render JSON with `@tiptap/static-renderer` to HTML on the server, KaTeX to HTML string (KaTeX has server-side `renderToString`, verified in KaTeX docs only by general knowledge; not re-read), use stored SVG for figures, then print with headless Chromium. Chromium tool not evaluated here; pick one in implementation planning.
- Word: three routes.
  1. Tiptap Conversion DOCX export: paid Pro package, Beta; its content reference has a "Math and equations" section (https://tiptap.dev/docs/conversion/import-export/docx); price and exact math support not verified.
  2. BlockNote DOCX exporter: GPL or paid (195 USD/month Business plan), only if BlockNote is the editor.
  3. Build it: `docx` 9.15.0 (2026-10-27, MIT, npm) in a Node worker, or Pandoc. Pandoc docs say math "will be rendered using OMML math markup" for DOCX (https://pandoc.org/MANUAL.html), which gives editable Word equations from LaTeX. Pandoc is GPL but running it as a separate server process does not link it to the SaaS code; confirm with counsel. Pandoc needs HTML or Markdown input, so a JSON to HTML step is still required. Figures go in as the stored SVG/PNG.
- Recommendation: route 3 with the LaTeX-in-node design; it avoids a recurring licence fee and keeps equations editable in Word.

## 6. Vietnamese and accessibility checklist (all unverified by test)

- Test Vietnamese diacritics in: KaTeX `\text{}`, mhchem labels, JSXGraph labels, Ketcher text, SVG export fonts (embed a font such as Noto Sans/Be Vietnam Pro in the PDF pipeline).
- Every figure node requires `alt` text; every formula needs a MathML/LaTeX text alternative.

## 7. Open items for planning

1. Legal read of PhET's current licence page and a quote if physics simulations are required.
2. Desmos API ToS (rendered page) only if graphing UX from Desmos is demanded. Otherwise leave out.
3. Confirm JSXGraph spec JSON design and SVG snapshot approach with a spike. *Update 2026-10-31:* JSXGraph renders to SVG by default and ships a snapshot example (https://github.com/jsxgraph/jsxgraph/blob/main/examples/snapshot.html), so the snapshot side is supported; the JSON spec is still ours to design.
4. ~~Confirm Ketcher SVG/PNG export.~~ *Resolved 2026-10-31:* `ketcher.generateImage(data, { outputFormat: 'svg' | 'png', backgroundColor, bondThickness })` returns a Blob (Ketcher README, https://github.com/epam/ketcher/blob/master/README.md). No extra library needed.
5. Decide Chromium vs WeasyPrint for PDF; confirm Pandoc OMML output for Vietnamese text.
6. Counsel review of the GPL tool (Pandoc) usage as an external process.

## Sources

- Tiptap: https://tiptap.dev/docs/editor/core-concepts/persistence , https://tiptap.dev/docs/editor/extensions/nodes/mathematics , https://tiptap.dev/docs/conversion/import-export/docx
- BlockNote: https://www.blocknotejs.org/pricing
- GeoGebra: https://github.com/geogebra/legal/blob/main/geogebra_license.md , https://geogebra.github.io/docs/reference/en/GeoGebra_Apps_Embedding/ , https://geogebra.github.io/docs/reference/en/GeoGebra_Apps_API/
- Desmos: https://www.desmos.com/api/v1.11/docs/index.html
- JSXGraph: https://github.com/jsxgraph/jsxgraph
- ChemDoodle: https://web.chemdoodle.com/installation/license , https://web.chemdoodle.com/store/proprietary-licensing
- PhET: https://phet.colorado.edu/en/licensing/html , https://phet.colorado.edu/en/help-center/getting-started
- Ketcher: https://github.com/epam/ketcher
- KaTeX: https://github.com/KaTeX/KaTeX (LICENSE, contrib/mhchem/README.md)
- MathLive: https://github.com/arnog/mathlive
- Kekule.js: https://github.com/partridgejiang/Kekule.js
- 3Dmol.js: https://github.com/3dmol/3Dmol.js ; Mol*: https://github.com/molstar/molstar
- Pandoc: https://pandoc.org/MANUAL.html
- Versions/licences: npm registry https://registry.npmjs.org/ for each package named above
